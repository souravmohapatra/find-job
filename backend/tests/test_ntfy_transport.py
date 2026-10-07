import httpx
import pytest
from app.config import get_settings
from app.notifications import transport


def configure(monkeypatch, tmp_path, handler):
    settings = get_settings()
    monkeypatch.setattr(settings, "notification_mode", "live")
    monkeypatch.setattr(settings, "ntfy_url", "http://ntfy.local")
    monkeypatch.setattr(settings, "notification_app_url", "https://jobs.example")
    path = tmp_path / "publisher-token"
    path.write_text("synthetic-token")
    monkeypatch.setattr(settings, "ntfy_token_file", path)
    original = httpx.Client
    monkeypatch.setattr(
        transport.httpx,
        "Client",
        lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs),
    )
    return transport.target()


def test_valid_receipt_and_no_redirect_or_environment_proxy(monkeypatch, tmp_path):
    calls = []

    def handler(request):
        calls.append(request)
        assert request.headers["Authorization"] == "Bearer synthetic-token"
        assert request.headers["Click"] == "https://jobs.example/jobs"
        assert request.content == "Synthetic message é".encode()
        return httpx.Response(
            200, json={"id": "receipt-1", "event": "message", "topic": "jobfinder"}
        )

    target = configure(monkeypatch, tmp_path, handler)
    assert transport.publish(target, "Synthetic message é").remote_id == "receipt-1"
    assert len(calls) == 1 and str(calls[0].url) == "http://ntfy.local/jobfinder"


@pytest.mark.parametrize(
    "status,state,retry",
    [
        (302, "failed", False),
        (401, "failed", False),
        (429, "failed", True),
        (500, "unknown", False),
        (200, "unknown", False),
    ],
)
def test_rejection_ambiguity_and_invalid_receipts(monkeypatch, tmp_path, status, state, retry):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            status, headers={"location": "https://elsewhere.example", "retry-after": "120"}, json={}
        )

    target = configure(monkeypatch, tmp_path, handler)
    outcome = transport.publish(target, "Synthetic message")
    assert outcome.state == state and outcome.retryable == retry
    assert len(calls) == 1


@pytest.mark.parametrize(
    "error,state,retry",
    [
        (httpx.ConnectError, "failed", True),
        (httpx.ReadTimeout, "unknown", False),
        (httpx.WriteError, "unknown", False),
    ],
)
def test_network_failure_classification(monkeypatch, tmp_path, error, state, retry):
    def handler(request):
        raise error("Synthetic transport failure", request=request)

    target = configure(monkeypatch, tmp_path, handler)
    outcome = transport.publish(target, "Synthetic message")
    assert outcome.state == state and outcome.retryable == retry


def test_destination_change_does_not_send_current_secret_to_old_origin(monkeypatch, tmp_path):
    target = configure(monkeypatch, tmp_path, lambda request: pytest.fail("No HTTP expected"))
    monkeypatch.setattr(get_settings(), "ntfy_url", "http://other.local")
    assert transport.publish(target, "Synthetic message").code == "notification_destination_changed"


def test_unicode_message_is_bounded_and_keeps_total_counts():
    body = transport.message(
        {
            "counts": {"new": 123},
            "companies": {str(i): {"label": "界" * 200, "count": 1} for i in range(30)},
        },
        "mock",
    )
    assert len(body.encode()) < 4096 and "123 new shortlisted" in body
    assert body.endswith("Open the full shortlist for all results.")


def test_retry_after_preserves_long_cooldown_and_http_dates():
    from datetime import UTC, datetime, timedelta
    from email.utils import format_datetime

    assert transport.retry_delay("7200") == 7200
    assert transport.retry_delay("0" * 100 + "7200") == 7200
    assert transport.retry_delay("9" * 100) == 315_576_000_000
    future = format_datetime(datetime.now(UTC) + timedelta(hours=2), usegmt=True)
    assert 7198 <= transport.retry_delay(future) <= 7201
    assert transport.retry_delay("invalid") == 60
