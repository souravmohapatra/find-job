from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from uuid import UUID

import httpx
import pytest
from app.collection import search as provider
from app.collection.discovery import begin
from app.collection.models import Company, DiscoveryRun, SearchRequest, SearchState, Source
from app.config import get_settings
from app.db import get_engine
from app.profile_models import Operation, now
from app.services.operations import OperationError, process_operation
from sqlalchemy import func, select
from sqlalchemy.orm import Session


@pytest.fixture
def live(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    key = tmp_path / "brave-key"
    key.write_text("synthetic-search-credential")
    monkeypatch.setattr(get_settings(), "search_mode", "live")
    monkeypatch.setattr(get_settings(), "brave_key_file", key)


def run() -> UUID:
    with Session(get_engine()) as db, db.begin():
        company = Company(label="Example Studio")
        db.add(company)
        db.flush()
        begin(db, company)
        return db.scalar(select(DiscoveryRun.id).where(DiscoveryRun.company_id == company.id))


def payload() -> dict:
    return {
        "web": {
            "results": [
                {
                    "title": "<b>Example careers</b>",
                    "url": "https://example.com/careers?utm_source=web",
                },
                {"title": "Duplicate", "url": "https://example.com/careers"},
                {"title": "Private", "url": "http://127.0.0.1/admin"},
                {"title": "Different Example", "url": "https://another.example/jobs"},
            ]
        }
    }


def transport(monkeypatch: pytest.MonkeyPatch, handler) -> None:
    monkeypatch.setattr(
        provider, "client", lambda: httpx.Client(transport=httpx.MockTransport(handler))
    )


def reset_spacing() -> None:
    with Session(get_engine()) as db, db.begin():
        db.get(SearchState, 1).next_allowed_at = now() - timedelta(seconds=1)


def test_fixed_endpoint_safe_candidates_and_replay_without_another_request(live, monkeypatch):
    calls = []

    def handle(request):
        calls.append(request)
        assert str(request.url).startswith(provider.ENDPOINT + "?")
        assert request.headers["X-Subscription-Token"] == "synthetic-search-credential"
        assert request.url.params["q"] == '"Example Studio" careers jobs'
        assert "freshness" not in request.url.params
        return httpx.Response(200, json=payload())

    transport(monkeypatch, handle)
    identifier = run()
    first = provider.search(identifier, 0, '"Example Studio" careers jobs')
    second = provider.search(identifier, 0, '"Example Studio" careers jobs')
    assert first == second and len(calls) == 1
    assert len(first) == 2 and first[0]["title"] == "Example careers"
    assert all(row["status"] == "needs_identity_review" for row in first)
    with Session(get_engine()) as db:
        assert db.scalar(select(SearchRequest)).state == "succeeded"
        assert db.scalar(select(Source)) is None


def test_name_only_operation_retains_ambiguous_leads_without_selecting_company(live, monkeypatch):
    transport(monkeypatch, lambda request: httpx.Response(200, json=payload()))
    identifier = run()
    with Session(get_engine()) as db:
        operation = db.scalar(select(Operation).where(Operation.kind == "discovery_step"))
        operation_id = operation.id
    process_operation(operation_id)
    process_operation(operation_id)
    with Session(get_engine()) as db:
        epoch = db.get(DiscoveryRun, identifier)
        company = db.get(Company, epoch.company_id)
        assert epoch.state == "partial" and len(epoch.candidates) == 2
        assert company.resolution == "needs_review" and company.website is None
        assert db.scalar(select(func.count()).select_from(SearchRequest)) == 1
        assert db.scalar(select(Source)) is None


def test_timeout_is_counted_and_not_reissued(live, monkeypatch):
    calls = []

    def timeout(request):
        calls.append(True)
        raise httpx.ReadTimeout("synthetic", request=request)

    transport(monkeypatch, timeout)
    identifier = run()
    for _ in range(2):
        with pytest.raises(OperationError) as failure:
            provider.search(identifier, 0, "Example careers")
        assert failure.value.code == "search_outcome_unknown"
    assert calls == [True]
    with Session(get_engine()) as db:
        assert db.scalar(select(SearchRequest)).state == "failed"


def test_global_budget_serializes_competing_reservations(live, monkeypatch):
    monkeypatch.setattr(get_settings(), "search_daily_limit", 1)
    transport(monkeypatch, lambda request: httpx.Response(200, json={"web": {"results": []}}))
    identifiers = [run(), run()]

    def attempt(identifier):
        try:
            provider.search(identifier, 0, "Example careers")
            return "success"
        except OperationError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(attempt, identifiers)) == ["search_budget", "success"]
    with Session(get_engine()) as db:
        assert db.scalar(select(func.count()).select_from(SearchRequest)) == 1


def test_monthly_budget_and_unknown_reservation_are_conservative(live, monkeypatch):
    monkeypatch.setattr(get_settings(), "search_monthly_limit", 1)
    identifier = run()
    with Session(get_engine()) as db, db.begin():
        db.add(SearchRequest(run_id=identifier, slot=0, query="Example", requested_at=now()))
    with pytest.raises(OperationError) as failure:
        provider.search(identifier, 0, "Example")
    assert failure.value.code == "search_outcome_unknown"
    with pytest.raises(OperationError) as failure:
        provider.search(identifier, 1, "Example jobs")
    assert failure.value.code == "search_budget"


def test_persisted_provider_cooldown_prevents_new_requests(live, monkeypatch):
    calls = []

    def limited(request):
        calls.append(True)
        return httpx.Response(429, headers={"Retry-After": "7200"})

    transport(monkeypatch, limited)
    identifier = run()
    with pytest.raises(OperationError) as failure:
        provider.search(identifier, 0, "Example careers")
    assert failure.value.code == "search_rate_limited"
    with pytest.raises(OperationError) as failure:
        provider.search(identifier, 1, "Example jobs")
    assert failure.value.code == "search_cooldown" and failure.value.retry_after > 7100
    assert calls == [True]
    with Session(get_engine()) as db:
        assert db.scalar(select(func.count()).select_from(SearchRequest)) == 1


def test_missing_key_and_mock_mode_do_not_reserve_or_call(monkeypatch, tmp_path):
    identifier = run()
    with pytest.raises(OperationError) as failure:
        provider.search(identifier, 0, "Example")
    assert failure.value.code == "search_mock_mode"
    monkeypatch.setattr(get_settings(), "search_mode", "live")
    monkeypatch.setattr(get_settings(), "brave_key_file", tmp_path / "missing")
    with pytest.raises(OperationError) as failure:
        provider.search(identifier, 0, "Example")
    assert failure.value.code == "search_unconfigured"
    with Session(get_engine()) as db:
        assert db.scalar(select(func.count()).select_from(SearchRequest)) == 0


@pytest.mark.parametrize(
    "status,body,code",
    [
        (302, {}, "search_provider_error"),
        (401, {}, "search_provider_error"),
        (200, {"invalid": True}, "search_invalid_response"),
    ],
)
def test_invalid_response_and_redirect_are_not_candidates(live, monkeypatch, status, body, code):
    transport(
        monkeypatch,
        lambda request: httpx.Response(status, json=body, headers={"Location": "http://127.0.0.1"}),
    )
    with pytest.raises(OperationError) as failure:
        provider.search(run(), 0, "Example")
    assert failure.value.code == code


def test_candidate_confirmation_requires_current_revision_and_owner_choice(
    live, monkeypatch, client
):
    from test_inventory_api import auth

    transport(monkeypatch, lambda request: httpx.Response(200, json=payload()))
    identifier = run()
    with Session(get_engine()) as db:
        operation_id = db.scalar(select(Operation.id).where(Operation.kind == "discovery_step"))
        company_id = db.get(DiscoveryRun, identifier).company_id
    process_operation(operation_id)
    headers = auth(client)
    endpoint = f"/api/v1/companies/{company_id}/discovery/{identifier}/confirm"
    choice = {"url": "https://example.com/careers", "confirmed_company": True}
    assert client.post(endpoint, headers=headers, json=choice).status_code == 428
    headers |= {"If-Match": '"1"'}
    assert (
        client.post(
            endpoint, headers=headers, json={**choice, "confirmed_company": False}
        ).status_code
        == 422
    )
    assert (
        client.post(
            endpoint, headers=headers, json={**choice, "url": "https://unrelated.example/"}
        ).status_code
        == 422
    )
    result = client.post(endpoint, headers=headers, json=choice)
    assert result.status_code == 202
    assert client.post(endpoint, headers=headers, json=choice).status_code == 409
    with Session(get_engine()) as db:
        company = db.get(Company, company_id)
        assert company.website == choice["url"] and company.revision == 2
        assert db.scalar(select(Source)) is None
        assert db.get(Operation, UUID(result.json()["operation_id"])).kind == "company_discover"
