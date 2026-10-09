import asyncio
import gzip
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.fetcher import governor
from app.fetcher import http as fetch_http
from app.fetcher.contracts import FetchFailure, FetchRequest, FetchResult
from app.fetcher.http import Fetcher, body_bytes
from app.fetcher.main import create_app
from app.fetcher.settings import FetchSettings


class Stream(httpx.AsyncByteStream):
    def __init__(self, body: bytes):
        self.body = body

    async def __aiter__(self):
        yield self.body


def setup_fetcher(tmp_path, monkeypatch, handler):
    config = FetchSettings(state_file=tmp_path / "origins.sqlite3", isolation_verified=True)
    fetcher = Fetcher(config)
    calls = []

    async def public(url, *args, **kwargs):
        calls.append(url)

    monkeypatch.setattr(fetch_http, "resolve_public", public)
    monkeypatch.setattr(governor, "reserve", lambda *args: 0)
    monkeypatch.setattr(
        fetcher, "client", lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )
    return fetcher, calls


def test_fetcher_checks_robots_redirects_and_does_not_forward_cookies(tmp_path, monkeypatch):
    seen = []

    def handler(request):
        seen.append(request)
        if request.url.path == "/robots.txt":
            return httpx.Response(404, stream=Stream(b""))
        if request.url.path == "/jobs":
            return httpx.Response(
                302,
                headers={
                    "location": "https://other.example.com/list",
                    "set-cookie": "private=value",
                },
                stream=Stream(b""),
            )
        return httpx.Response(
            200,
            headers={
                "content-type": "application/json",
                "content-encoding": "gzip",
                "etag": "version1",
            },
            stream=Stream(gzip.compress(b'{"jobs": []}')),
        )

    fetcher, checked = setup_fetcher(tmp_path, monkeypatch, handler)
    result = asyncio.run(fetcher.fetch(FetchRequest(url="https://example.com/jobs", etag="old")))
    assert result.status == 200 and json.loads(result.body) == {"jobs": []}
    assert result.url == "https://other.example.com/list"
    assert len(checked) == 4 and len(seen) == 4
    assert seen[1].headers["if-none-match"] == "old"
    assert "if-none-match" not in seen[-1].headers
    assert all(
        "authorization" not in request.headers and "cookie" not in request.headers
        for request in seen
    )


def test_robots_denies_before_requesting_job_page(tmp_path, monkeypatch):
    paths = []

    def handler(request):
        paths.append(request.url.path)
        return httpx.Response(
            200, stream=Stream(b"User-agent: *\nDisallow: /private\nCrawl-delay: 5")
        )

    fetcher, _ = setup_fetcher(tmp_path, monkeypatch, handler)
    with pytest.raises(FetchFailure, match="robots_denied"):
        asyncio.run(fetcher.fetch(FetchRequest(url="https://example.com/private/jobs")))
    assert paths == ["/robots.txt"]
    assert fetcher.spacing["https://example.com"] == 5


def test_private_redirect_and_dns_answer_are_rejected(tmp_path, monkeypatch):
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404, stream=Stream(b""))
        return httpx.Response(
            302, headers={"location": "http://127.0.0.1/secrets"}, stream=Stream(b"")
        )

    fetcher, checked = setup_fetcher(tmp_path, monkeypatch, handler)
    with pytest.raises(FetchFailure, match="destination_denied"):
        asyncio.run(fetcher.fetch(FetchRequest(url="https://example.com/jobs")))
    assert not any("127.0.0.1" in url for url in checked)


@pytest.mark.parametrize("compressed", [False, True])
def test_decompressed_content_limit(compressed):
    async def run():
        body = b"a" * 2000
        response = httpx.Response(
            200,
            headers={"content-encoding": "gzip" if compressed else "identity"},
            stream=Stream(gzip.compress(body) if compressed else body),
        )
        try:
            return await body_bytes(response, 1000)
        finally:
            await response.aclose()

    with pytest.raises(FetchFailure, match="document_too_large"):
        asyncio.run(run())


def test_persistent_origin_spacing_and_retry_after(tmp_path):
    path = tmp_path / "state.sqlite3"
    assert governor.reserve(path, "https://example.com") == 0
    assert governor.reserve(path, "https://example.com") > 1.8
    governor.cooldown(path, "https://example.com", 120)
    with pytest.raises(FetchFailure) as failure:
        governor.reserve(path, "https://example.com")
    assert failure.value.retry_after >= 119
    assert path.stat().st_mode & 0o777 == 0o600


def test_fetch_service_auth_input_bounds_and_disabled_isolation_gate(tmp_path):
    token = tmp_path / "token"
    token.write_text("synthetic-fetcher-token-with-32-chars")
    config = FetchSettings(token_file=token, state_file=tmp_path / "state.sqlite3")
    with TestClient(create_app(config)) as client:
        assert client.post("/fetch", json={"url": "https://example.com"}).status_code == 401
        headers = {"Authorization": "Bearer " + token.read_text()}
        assert client.post("/fetch", headers=headers, content=b" " * 8193).status_code == 413
        assert (
            client.post(
                "/fetch", headers=headers, json={"url": "https://example.com", "profile": "private"}
            ).status_code
            == 422
        )
        response = client.post("/fetch", headers=headers, json={"url": "https://example.com"})
        assert response.status_code == 502 and response.json()["code"] == "isolation_not_verified"
        assert "synthetic-fetcher-token" not in response.text


def test_worker_rpc_and_inventory_error_semantics(tmp_path, monkeypatch):
    from app.collection import transport
    from app.services.operations import OperationError

    requests = []
    document = FetchResult(
        url="https://example.com/jobs",
        status=200,
        body='{"jobs": []}',
        content_type="application/json",
    )

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=document.model_dump())

    monkeypatch.setattr(
        transport,
        "client",
        lambda: httpx.Client(base_url="http://fetcher/", transport=httpx.MockTransport(handler)),
    )
    assert transport.fetch_json("https://example.com/jobs") == {"jobs": []}
    assert str(requests[0].url) == "http://fetcher/fetch"
    assert set(json.loads(requests[0].content)) == {"url", "etag", "modified_since"}
    document.status = 429
    document.retry_after = 120
    with pytest.raises(OperationError) as failure:
        transport.fetch_json("https://example.com/jobs")
    assert failure.value.retryable and failure.value.retry_after == 120
    document.status = 200
    document.body = "<html>Unavailable</html>"
    document.content_type = "text/html"
    with pytest.raises(OperationError, match="JSON inventory"):
        transport.fetch_json("https://example.com/jobs")


def test_dns_rejects_mixed_public_private_records(monkeypatch):
    async def run():
        async def addresses(*args, **kwargs):
            return [(2, 1, 6, "", ("93.184.216.34", 0)), (2, 1, 6, "", ("10.0.0.1", 0))]

        monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", addresses)
        await fetch_http.resolve_public("https://example.com/jobs")

    with pytest.raises(FetchFailure, match="destination_denied"):
        asyncio.run(run())


def test_fetcher_factory_requires_proxy_and_ignores_host_proxy_environment(monkeypatch, tmp_path):
    supplied = {}

    def factory(**kwargs):
        supplied.update(kwargs)
        return object()

    monkeypatch.setattr(httpx, "AsyncClient", factory)
    config = FetchSettings(state_file=tmp_path / "state.sqlite3")
    Fetcher(config).client()
    assert supplied["proxy"] == "http://egress-proxy:3128"
    assert supplied["trust_env"] is False and supplied["follow_redirects"] is False
    config.proxy_url = ""
    with pytest.raises(FetchFailure, match="proxy_not_configured"):
        Fetcher(config).client()


def test_robots_unavailable_and_retry_after_do_not_fetch_jobs(tmp_path, monkeypatch):
    paths = []

    def handler(request):
        paths.append(request.url.path)
        return httpx.Response(503, headers={"retry-after": "120"}, stream=Stream(b"Unavailable"))

    fetcher, _ = setup_fetcher(tmp_path, monkeypatch, handler)
    with pytest.raises(FetchFailure) as failure:
        asyncio.run(fetcher.fetch(FetchRequest(url="https://example.com/jobs")))
    assert failure.value.code == "robots_unavailable" and failure.value.retry_after == 120
    assert paths == ["/robots.txt"]
    import time

    db = governor.connection(fetcher.config.state_file)
    try:
        row = db.execute("SELECT cooldown FROM origins").fetchone()
        assert row[0] > time.time() + 110
    finally:
        db.close()


def test_long_origin_backoff_is_preserved_while_worker_retry_is_bounded(tmp_path, monkeypatch):
    import time

    seconds = fetch_http.retry_delay(str(60 * 86400))
    assert seconds == 60 * 86400
    path = tmp_path / "state.sqlite3"
    governor.cooldown(path, "https://example.com", seconds)
    db = governor.connection(path)
    try:
        assert db.execute("SELECT cooldown FROM origins").fetchone()[0] > time.time() + 59 * 86400
    finally:
        db.close()

    from app.collection import transport
    from app.services.operations import OperationError

    monkeypatch.setattr(
        transport,
        "fetch_document",
        lambda request: FetchResult(
            url=request.url,
            status=429,
            body="",
            content_type="application/json",
            retry_after=seconds,
        ),
    )
    with pytest.raises(OperationError) as failure:
        transport.fetch_json("https://example.com/jobs")
    assert failure.value.retry_after == 30 * 86400


@pytest.mark.parametrize(
    "headers,cacheable",
    [
        ({}, True),
        ({"cache-control": "public, no-store"}, False),
        ({"vary": "Accept-Encoding"}, False),
        ({"vary": "*"}, False),
    ],
)
def test_304_without_body_ignores_representation_encoding(
    tmp_path, monkeypatch, headers, cacheable
):
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404, stream=Stream(b""))
        assert request.headers["if-none-match"] == '"v1"'
        return httpx.Response(
            304, headers={**headers, "content-encoding": "gzip", "etag": '"v1"'}, stream=Stream(b"")
        )

    fetcher, _ = setup_fetcher(tmp_path, monkeypatch, handler)
    result = asyncio.run(fetcher.fetch(FetchRequest(url="https://example.com/jobs", etag='"v1"')))
    assert result.status == 304 and result.body == "" and result.cacheable is cacheable


def test_redirect_back_to_original_still_reports_lost_conditional_headers(tmp_path, monkeypatch):
    count = 0

    def handler(request):
        nonlocal count
        if request.url.path == "/robots.txt":
            return httpx.Response(404, stream=Stream(b""))
        count += 1
        if count < 3:
            return httpx.Response(
                302, headers={"location": "/other" if count == 1 else "/jobs"}, stream=Stream(b"")
            )
        assert "if-none-match" not in request.headers
        return httpx.Response(304, stream=Stream(b""))

    fetcher, _ = setup_fetcher(tmp_path, monkeypatch, handler)
    result = asyncio.run(fetcher.fetch(FetchRequest(url="https://example.com/jobs", etag='"v1"')))
    assert result.url == "https://example.com/jobs" and result.redirected


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/admin",
        "http://192.168.1.1/router",
        "http://10.0.0.1/internal",
        "http://169.254.169.254/latest/meta-data",
        "http://[::1]/private",
        "http://[fe80::1]/link-local",
        "http://[fc00::1]/unique-local",
    ],
)
def test_resolve_public_rejects_private_ip_literals_immediately(url):
    with pytest.raises(FetchFailure, match="destination_denied"):
        asyncio.run(fetch_http.resolve_public(url, proxy_url="http://egress-proxy:3128"))


def test_resolve_public_delegates_to_proxy_when_local_dns_unavailable(monkeypatch):
    async def run():
        async def failing_dns(*args, **kwargs):
            raise OSError("name resolution failed on internal network")

        monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", failing_dns)
        # With proxy configured, resolve_public does not fail locally on source_dns
        await fetch_http.resolve_public(
            "https://example.com/jobs", proxy_url="http://egress-proxy:3128"
        )
        # Without proxy configured, local DNS failure raises source_dns
        with pytest.raises(FetchFailure, match="source_dns"):
            await fetch_http.resolve_public("https://example.com/jobs", proxy_url="")

    asyncio.run(run())


def test_squid_destination_denial_and_dns_failure_mapped_truthfully(tmp_path):
    config = FetchSettings(state_file=tmp_path / "origins.sqlite3", isolation_verified=True)

    # 403 Access Denied from Squid proxy is mapped to destination_denied
    def denied_handler(request):
        return httpx.Response(
            403, headers={"x-squid-error": "ERR_ACCESS_DENIED 0", "server": "squid/6.13"}
        )

    fetcher_denied = Fetcher(config)
    fetcher_denied.client = lambda: httpx.AsyncClient(transport=httpx.MockTransport(denied_handler))
    with pytest.raises(FetchFailure, match="destination_denied"):
        asyncio.run(fetcher_denied.fetch(FetchRequest(url="https://rebind.example.com/jobs")))

    # 503 DNS failure from Squid proxy is mapped to source_dns
    def dns_fail_handler(request):
        return httpx.Response(
            503, headers={"x-squid-error": "ERR_DNS_FAIL 0", "server": "squid/6.13"}
        )

    fetcher_dns_fail = Fetcher(config)
    fetcher_dns_fail.client = lambda: httpx.AsyncClient(
        transport=httpx.MockTransport(dns_fail_handler)
    )
    with pytest.raises(FetchFailure, match="source_dns"):
        asyncio.run(
            fetcher_dns_fail.fetch(FetchRequest(url="https://nonexistent.example.com/jobs"))
        )

    # HTTPS CONNECT ProxyError 403 is mapped to destination_denied
    def connect_error_handler(request):
        raise httpx.ProxyError("403 Forbidden while establishing CONNECT tunnel")

    fetcher_connect = Fetcher(config)
    fetcher_connect.client = lambda: httpx.AsyncClient(
        transport=httpx.MockTransport(connect_error_handler)
    )
    with pytest.raises(FetchFailure, match="destination_denied"):
        asyncio.run(
            fetcher_connect.fetch(FetchRequest(url="https://private-rebind.example.com/jobs"))
        )
