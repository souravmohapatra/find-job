import asyncio
import ipaddress
import socket
import zlib
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx
from app.collection.contracts import public_link
from app.fetcher import governor
from app.fetcher.contracts import MAX_BODY, FetchFailure, FetchRequest, FetchResult
from app.fetcher.settings import FetchSettings


def retry_delay(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        seconds = (
            int(value)
            if value.isdigit()
            else int((parsedate_to_datetime(value) - datetime.now(UTC)).total_seconds())
        )
        return max(
            0, min(seconds, 10**12)
        )  # Retain long holds; worker retries are bounded separately.
    except (ValueError, TypeError, OverflowError):
        return 60


async def resolve_public(url: str) -> None:
    host = urlsplit(public_link(url)).hostname
    assert host is not None
    try:
        records = await asyncio.get_running_loop().getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except OSError:
        raise FetchFailure("source_dns", retry_after=60) from None
    if not records or any(not ipaddress.ip_address(record[4][0]).is_global for record in records):
        raise FetchFailure("destination_denied")
    # Proxy destination ACLs must repeat this restriction at connection time.


async def body_bytes(response: httpx.Response, limit: int) -> bytes:
    encoding = response.headers.get("content-encoding", "identity").lower()
    if encoding not in {"identity", "gzip", "deflate"}:
        raise FetchFailure("unsupported_content_encoding")
    decoder = (
        zlib.decompressobj(31 if encoding == "gzip" else 15) if encoding != "identity" else None
    )
    output = bytearray()
    try:
        async for chunk in response.aiter_raw(chunk_size=65536):
            decoded = decoder.decompress(chunk, limit - len(output) + 1) if decoder else chunk
            output.extend(decoded)
            if len(output) > limit or (decoder and decoder.unconsumed_tail):
                raise FetchFailure("document_too_large")
        if decoder and (not decoder.eof or decoder.unused_data):
            raise FetchFailure("invalid_compressed_content")
    except zlib.error:
        raise FetchFailure("invalid_compressed_content") from None
    return bytes(output)


class Fetcher:
    def __init__(self, config: FetchSettings):
        self.config = config
        self.slots = asyncio.Semaphore(4)
        self.origins: dict[str, asyncio.Semaphore] = {}
        self.spacing: dict[str, float] = {}
        self.robots: dict[str, tuple[float, RobotFileParser]] = {}

    def client(self) -> httpx.AsyncClient:
        if not self.config.proxy_url.startswith("http://"):
            raise FetchFailure("proxy_not_configured")
        return httpx.AsyncClient(
            proxy=self.config.proxy_url,
            trust_env=False,
            timeout=30,
            follow_redirects=False,
            headers={"User-Agent": self.config.user_agent, "Accept-Encoding": "gzip, deflate"},
        )

    async def one(
        self, client: httpx.AsyncClient, url: str, headers: dict[str, str], limit: int
    ) -> FetchResult:
        url = public_link(url)
        await resolve_public(url)
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in self.origins:
            if len(self.origins) >= 4096:
                raise FetchFailure("origin_budget", retry_after=3600)
            self.origins[origin] = asyncio.Semaphore(2)
        async with self.slots, self.origins[origin]:
            delay = await asyncio.to_thread(
                governor.reserve, self.config.state_file, origin, self.spacing.get(origin, 2)
            )
            await asyncio.sleep(delay)
            # Build a fresh request so redirect responses cannot inject cookies into later hops.
            request = httpx.Request(
                "GET",
                url,
                headers={
                    "User-Agent": self.config.user_agent,
                    "Accept-Encoding": "gzip, deflate",
                    **headers,
                },
            )
            response = await client.send(request, stream=True)
            try:
                retry = retry_delay(response.headers.get("retry-after"))
                if response.status_code in {429, 503}:
                    retry = retry if retry is not None else 60
                    await asyncio.to_thread(
                        governor.cooldown, self.config.state_file, origin, retry
                    )
                if response.status_code in {301, 302, 303, 307, 308}:
                    target = response.headers.get("location")
                    if not target:
                        raise FetchFailure("invalid_redirect")
                    return FetchResult(
                        url=public_link(urljoin(url, target)),
                        status=response.status_code,
                        body="",
                        content_type="",
                    )
                raw = await body_bytes(response, limit)
                try:
                    body = raw.decode(response.encoding or "utf-8")
                except (UnicodeError, LookupError):
                    raise FetchFailure("unsupported_document_encoding") from None
                return FetchResult(
                    url=url,
                    status=response.status_code,
                    body=body,
                    content_type=response.headers.get("content-type", "")[:300],
                    etag=response.headers.get("etag", "")[:1000] or None,
                    modified=response.headers.get("last-modified", "")[:1000] or None,
                    retry_after=retry,
                )
            finally:
                await response.aclose()

    async def chain(
        self,
        client: httpx.AsyncClient,
        url: str,
        headers: dict[str, str],
        limit: int,
        *,
        robots: bool,
    ) -> FetchResult:
        for _ in range(6):
            if robots:
                await self.allowed(client, url)
            response = await self.one(client, url, headers, limit)
            if response.status not in {301, 302, 303, 307, 308}:
                return response
            url = response.url
            headers = {}  # Conditional validators never cross a redirect boundary.
        raise FetchFailure("redirect_limit")

    async def allowed(self, client: httpx.AsyncClient, url: str) -> None:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        clock = asyncio.get_running_loop().time()
        cached = self.robots.get(origin)
        if cached and cached[0] > clock:
            parser = cached[1]
        else:
            response = await self.chain(
                client, origin + "/robots.txt", {}, 512 * 1024, robots=False
            )
            if response.status in {401, 403}:
                raise FetchFailure("robots_denied")
            if response.status == 429 or response.status >= 500:
                raise FetchFailure("robots_unavailable", retry_after=response.retry_after or 60)
            if response.status not in {200, 404, 410}:
                raise FetchFailure("robots_unavailable", retry_after=3600)
            parser = RobotFileParser()
            parser.parse(response.body.splitlines() if response.status == 200 else [])
            if len(self.robots) >= 4096:
                self.robots = {key: value for key, value in self.robots.items() if value[0] > clock}
                if len(self.robots) >= 4096:
                    raise FetchFailure("origin_budget", retry_after=3600)
            self.robots[origin] = (clock + 3600, parser)
        crawl = parser.crawl_delay("JobFinder") or 0
        rate = parser.request_rate("JobFinder")
        spacing = max(
            2.0, float(crawl), rate.seconds / rate.requests if rate and rate.requests else 0
        )
        self.spacing[origin] = spacing
        if not parser.can_fetch("JobFinder", url):
            raise FetchFailure("robots_denied")

    async def fetch(self, request: FetchRequest) -> FetchResult:
        if not self.config.isolation_verified:
            raise FetchFailure("isolation_not_verified")
        try:
            async with asyncio.timeout(30), self.client() as client:
                headers = {}
                if request.etag:
                    headers["If-None-Match"] = request.etag
                if request.modified_since:
                    headers["If-Modified-Since"] = request.modified_since
                return await self.chain(client, request.url, headers, MAX_BODY, robots=True)
        except ValueError:
            raise FetchFailure("destination_denied") from None
        except (TimeoutError, httpx.HTTPError):
            raise FetchFailure("source_transport", retry_after=60) from None
