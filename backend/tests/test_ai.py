"""Synthetic OpenRouter contract tests: all HTTP uses MockTransport, never a live key."""

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import provider
from app.ai.contracts import TaskConfig
from app.ai.decisions import ChoiceAnswer, NoulAnswer, ScoreAnswer
from app.ai.models import AiLimitsRow, InferenceCall, TaskRevision
from app.ai.run_ledger import TOTAL_REQUESTS, BudgetRefused, RunLedger
from app.ai.tasks import Probe, reconcile_call, validate_task
from app.config import get_settings
from app.db import get_engine
from app.domain.profile import Evidence, Facts
from app.profile_models import Operation, now
from app.services.operations import OperationError, process_operation


def auth(client: TestClient) -> dict[str, str]:
    result = client.post(
        "/api/v1/auth/login",
        json={"username": "owner", "password": "synthetic-test-password"},
        headers={"Origin": "https://testserver"},
    )
    assert result.status_code == 200
    return {"Origin": "https://testserver", "X-CSRF-Token": result.json()["csrf_token"]}


def configuration(model: str = "example/profile", **overrides: Any) -> UUID:
    config = TaskConfig(model=model, **overrides)
    with Session(get_engine()) as db, db.begin():
        row = TaskRevision(
            task="profile_analysis", revision=1, config=config.model_dump(mode="json")
        )
        db.add(row)
        db.flush()
        return row.id


def completion(content: object = None, **overrides: Any) -> dict[str, Any]:
    return {
        "id": "gen-synthetic",
        "model": "example/profile",
        "provider": "Example",
        "choices": [
            {
                "finish_reason": "stop",
                "message": {"content": json.dumps(content or {"status": "ok"})},
            }
        ],
        "usage": {"prompt_tokens": 12, "completion_tokens": 5, "cost": 0.001},
        **overrides,
    }


@pytest.fixture
def transport(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict[str, Any]:
    state: dict[str, Any] = {
        "posts": [],
        "urls": [],
        "responses": [completion()],
        "parameters": ["response_format", "structured_outputs", "temperature", "reasoning"],
        "price": "0.000001",
        "get_count": 0,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            state["get_count"] += 1
            if request.url.path.endswith("/generation"):
                return httpx.Response(
                    200, json={"data": {"id": "gen-synthetic", "total_cost": 0.002}}
                )
            return httpx.Response(
                200,
                json={
                    "data": {
                        "endpoints": [
                            {
                                "tag": "example",
                                "supported_parameters": state["parameters"],
                                "context_length": 128000,
                                "pricing": {
                                    "prompt": state["price"],
                                    "completion": "0.000002",
                                    "request": "0",
                                },
                            }
                        ]
                    }
                },
            )
        state["urls"].append(str(request.url))
        state["posts"].append(json.loads(request.content))
        response = state["responses"].pop(0)
        if isinstance(response, Exception):
            raise response
        if isinstance(response, httpx.Response):
            return response
        return httpx.Response(200, json=response)

    monkeypatch.setattr(
        provider,
        "client",
        lambda: httpx.Client(base_url=provider.BASE_URL, transport=httpx.MockTransport(handler)),
    )
    monkeypatch.setattr(get_settings(), "live_ledger_path", tmp_path / "run-ledger.json")
    return state


def run(config: UUID) -> Probe:
    return provider.infer("profile_analysis", config, None, "Synthetic test", {"test": True}, Probe)


def test_config_independent_revisions_conflicts_and_secret_boundary(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    assert client.get("/api/v1/settings/ai").status_code == 401
    key = tmp_path / "key"
    key.write_text("synthetic-secret-never-returned")
    monkeypatch.setattr(get_settings(), "openrouter_key_file", key)
    headers = auth(client)
    initial = client.get("/api/v1/settings/ai").json()
    assert initial["key_configured"] and all(t["config"]["model"] is None for t in initial["tasks"])
    for task in ["profile_analysis", "job_extraction", "job_matching"]:
        body = {"task": task, "config": {"model": f"example/{task}"}}
        assert client.patch("/api/v1/settings/ai", headers=headers, json=body).status_code == 428
        response = client.patch(
            "/api/v1/settings/ai", headers={**headers, "If-Match": '"0"'}, json=body
        )
        assert response.status_code == 200
        assert (
            client.patch(
                "/api/v1/settings/ai", headers={**headers, "If-Match": '"0"'}, json=body
            ).status_code
            == 409
        )
    assert "synthetic-secret" not in response.text
    with Session(get_engine()) as db:
        assert len(list(db.scalars(select(TaskRevision)))) == 3
        assert db.scalar(select(Operation).where(Operation.kind == "profile_reassess"))
    assert (
        client.patch(
            "/api/v1/settings/ai",
            headers={**headers, "If-Match": '"1"'},
            json={"task": "profile_analysis", "config": {"model": "openrouter/auto"}},
        ).status_code
        == 422
    )


def test_request_contract_provenance_and_cost(transport: dict[str, Any]) -> None:
    identifier = configuration(zdr=True, temperature=0, reasoning_effort="low")
    assert run(identifier).status == "ok"
    request = transport["posts"][0]
    assert request["model"] == "example/profile" and "models" not in request
    assert request["provider"]["data_collection"] == "deny"
    assert request["provider"]["zdr"] and request["provider"]["require_parameters"]
    assert request["provider"]["max_price"] == {"prompt": 20, "completion": 60, "request": 0}
    assert request["response_format"]["json_schema"]["strict"]
    assert not {"tools", "plugins", "transforms"} & request.keys()
    with Session(get_engine()) as db:
        call = db.scalar(select(InferenceCall))
        assert call and call.state == "succeeded" and call.reported_usd == Decimal(".001")
        assert call.reserved_usd == Decimal(".56") and call.provider == "Example"
        assert call.generation_id == "gen-synthetic" and call.config_id == identifier
        assert not {"prompt", "response", "content"} & set(InferenceCall.__table__.columns.keys())


def test_one_charged_repair_same_configuration(transport: dict[str, Any]) -> None:
    identifier = configuration()
    transport["responses"] = [completion({"status": "bad"}), completion()]
    assert run(identifier).status == "ok"
    assert len(transport["posts"]) == 2
    assert transport["posts"][0]["model"] == transport["posts"][1]["model"]
    with Session(get_engine()) as db:
        calls = list(db.scalars(select(InferenceCall).order_by(InferenceCall.created_at)))
        assert [call.state for call in calls] == ["invalid", "succeeded"]
        assert sum(call.reported_usd for call in calls) == Decimal(".002")


def test_invalid_output_stops_after_one_repair(transport: dict[str, Any]) -> None:
    identifier = configuration()
    transport["responses"] = [completion({"status": "bad"}), completion({"status": "bad"})]
    with pytest.raises(OperationError, match="invalid or unsupported facts twice"):
        run(identifier)
    assert len(transport["posts"]) == 2


@pytest.mark.parametrize("change", ["capability", "pricing", "input"])
def test_incompatible_or_incomplete_input_never_sent(
    transport: dict[str, Any], change: str
) -> None:
    identifier = configuration()
    if change == "capability":
        transport["parameters"] = ["temperature"]
    elif change == "pricing":
        transport["price"] = None
    with pytest.raises(OperationError):
        provider.infer(
            "profile_analysis",
            identifier,
            None,
            "Synthetic",
            "x" * 30000 if change == "input" else "short",
            Probe,
        )
    assert transport["posts"] == []
    with Session(get_engine()) as db:
        assert db.scalar(select(InferenceCall)) is None


@pytest.mark.parametrize(
    "status,code",
    [
        (401, "ai_authentication"),
        (402, "ai_credits"),
        (404, "ai_configuration"),
        (429, "ai_rate_limited"),
        (503, "ai_unavailable"),
    ],
)
def test_provider_errors_sanitized_and_cooldown(
    transport: dict[str, Any], status: int, code: str
) -> None:
    identifier = configuration()
    transport["responses"] = [
        httpx.Response(
            status,
            headers={"Retry-After": "180"},
            json={"error": {"message": "DO NOT ECHO PRIVATE PROVIDER CONTENT"}},
        )
    ]
    with pytest.raises(OperationError) as captured:
        run(identifier)
    assert captured.value.code == code and "PRIVATE" not in str(captured.value)
    if status == 429:
        assert captured.value.retry_after == 180
        with pytest.raises(OperationError) as second:
            run(identifier)
        assert second.value.retry_after and second.value.retry_after > 175
        assert len(transport["posts"]) == 1
    with Session(get_engine()) as db:
        row = db.scalar(select(InferenceCall))
        assert row
        assert row.reported_usd == (None if status == 503 else 0)
        if status in {401, 402, 404}:
            assert db.get(TaskRevision, identifier).validation_state == "blocked"


def test_unknown_billing_blocks_then_reconciles(transport: dict[str, Any]) -> None:
    identifier = configuration()
    transport["responses"] = [completion(usage={"prompt_tokens": 10})]
    with pytest.raises(OperationError) as captured:
        run(identifier)
    assert captured.value.code == "ai_cost_unknown"
    with pytest.raises(OperationError):
        run(identifier)
    assert len(transport["posts"]) == 1
    with Session(get_engine()) as db:
        row = db.scalar(select(InferenceCall))
        assert row and row.state == "unknown" and row.reserved_usd > 0
        call_id = row.id
    reconcile_call(call_id)
    transport["responses"] = [completion()]
    assert run(identifier).status == "ok"
    with Session(get_engine()) as db:
        assert db.get(InferenceCall, call_id).reported_usd == Decimal(".002")


def test_timeout_keeps_reservation(transport: dict[str, Any]) -> None:
    identifier = configuration()
    transport["responses"] = [httpx.ReadTimeout("private diagnostic")]
    with pytest.raises(OperationError) as captured:
        run(identifier)
    assert captured.value.code == "ai_transport"
    with Session(get_engine()) as db:
        call = db.scalar(select(InferenceCall))
        assert call and call.state == "unknown" and call.reported_usd is None


def test_cumulative_ledger_blocks_dispatch_without_a_request(
    transport: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    identifier = configuration()
    monkeypatch.setattr(get_settings(), "integration_mode", "live")
    ledger = RunLedger(get_settings().live_ledger_path)
    for index in range(TOTAL_REQUESTS):
        ledger.admit(f"prefill-{index}", Decimal("0.001"))
        ledger.settle(f"prefill-{index}", Decimal(0))
    with pytest.raises(OperationError) as raised:
        run(identifier)
    assert raised.value.code == "ai_budget"
    assert transport["posts"] == []
    with Session(get_engine()) as db:
        call = db.get(InferenceCall, db.scalar(select(InferenceCall.id)))
        assert call and call.state == "failed" and call.reported_usd == Decimal(0)


def test_live_calls_settle_the_cumulative_ledger(
    transport: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    identifier = configuration()
    monkeypatch.setattr(get_settings(), "integration_mode", "live")
    assert run(identifier).status == "ok"
    summary = RunLedger(get_settings().live_ledger_path).summary()
    assert summary["attempts"] == 1
    assert summary["known_usd"] == "0.001"
    assert summary["held_usd"] == "0"
    assert summary["unresolved_calls"] == []


def test_live_transport_failure_keeps_ledger_cost_held(
    transport: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    identifier = configuration()
    monkeypatch.setattr(get_settings(), "integration_mode", "live")
    transport["responses"] = [httpx.ConnectError("synthetic network failure")]
    with pytest.raises(OperationError) as raised:
        run(identifier)
    assert raised.value.code == "ai_transport"
    summary = RunLedger(get_settings().live_ledger_path).summary()
    assert summary["attempts"] == 1
    assert len(summary["unresolved_calls"]) == 1
    assert Decimal(summary["held_usd"]) > 0


def test_reservations_serialize_budget_and_concurrency() -> None:
    identifier = configuration()
    with Session(get_engine()) as db, db.begin():
        db.add(AiLimitsRow(settings={"daily_calls": 500, "daily_usd": ".60"}))

    def attempt() -> str:
        try:
            provider.reserve(
                identifier,
                "profile_analysis",
                TaskConfig(model="example/profile"),
                None,
                "v1",
                "v1",
            )
            return "reserved"
        except OperationError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: attempt(), range(2)))
    assert sorted(results) == ["ai_budget", "reserved"]


def test_live_cv_uses_captured_model_and_validates_evidence(
    client: TestClient, transport: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    identifier = configuration()
    monkeypatch.setattr(get_settings(), "integration_mode", "live")
    headers = auth(client)
    cv = b"Synthetic nurse\nClinical education\nemail@example.test"
    result = client.post(
        "/api/v1/profile/documents",
        headers=headers,
        files={"file": ("cv.txt", cv)},
        data={"consent": "true"},
    )
    assert result.status_code == 202
    with Session(get_engine()) as db, db.begin():
        original = db.get(TaskRevision, identifier)
        db.add(
            TaskRevision(
                task="profile_analysis",
                revision=2,
                config={**original.config, "model": "example/replacement"},
            )
        )
    invalid = Facts(summary="Nursing", summary_evidence=[Evidence(span_id="s1", quote="Not in CV")])
    valid = Facts(
        summary="Nursing", summary_evidence=[Evidence(span_id="s1", quote="Synthetic nurse")]
    )
    transport["responses"] = [
        completion(invalid.model_dump(mode="json")),
        completion(valid.model_dump(mode="json")),
    ]
    process_operation(UUID(result.json()["operation_id"]))
    operation = client.get(result.json()["status_url"]).json()
    assert operation["state"] == "succeeded", operation
    assert len(transport["posts"]) == 2
    assert all(request["model"] == "example/profile" for request in transport["posts"])
    assert all("email@example.test" not in json.dumps(request) for request in transport["posts"])


def test_switching_mock_upload_to_live_requires_new_consent(
    client: TestClient, transport: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = auth(client)
    result = client.post(
        "/api/v1/profile/documents", headers=headers, files={"file": ("cv.txt", b"Synthetic nurse")}
    )
    monkeypatch.setattr(get_settings(), "integration_mode", "live")
    process_operation(UUID(result.json()["operation_id"]))
    operation = client.get(result.json()["status_url"]).json()
    assert operation["state"] == "blocked" and operation["error_code"] == "consent_required"
    assert not transport["posts"]


def test_operation_retry_after_persisted(
    client: TestClient, transport: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    configuration()
    monkeypatch.setattr(get_settings(), "integration_mode", "live")
    headers = auth(client)
    result = client.post(
        "/api/v1/settings/ai/validate",
        headers=headers,
        json={"task": "profile_analysis", "acknowledge_cost": True},
    )
    assert result.status_code == 202
    transport["responses"] = [httpx.Response(429, headers={"Retry-After": "600"})]
    process_operation(UUID(result.json()["operation_id"]))
    with Session(get_engine()) as db:
        operation = db.get(Operation, UUID(result.json()["operation_id"]))
        assert operation.state == "queued" and operation.available_at > now() + timedelta(
            seconds=595
        )


def test_explicit_fallback_keeps_privacy_and_records_actual_model(
    transport: dict[str, Any],
) -> None:
    identifier = configuration(fallback_models=["example/fallback"], zdr=True)
    transport["responses"] = [completion(model="example/fallback")]
    assert run(identifier).status == "ok"
    request = transport["posts"][0]
    assert request["models"] == ["example/profile", "example/fallback"]
    assert request["provider"]["data_collection"] == "deny" and request["provider"]["zdr"]
    with Session(get_engine()) as db:
        assert db.scalar(select(InferenceCall)).returned_model == "example/fallback"


def test_stalled_reservation_survives_blocked_retry() -> None:
    identifier = configuration()
    call_id = provider.reserve(
        identifier, "profile_analysis", TaskConfig(model="example/profile"), None, "v1", "v1"
    )
    with Session(get_engine()) as db, db.begin():
        db.get(InferenceCall, call_id).created_at = now() - timedelta(minutes=6)
    with pytest.raises(OperationError) as captured:
        provider.reserve(
            identifier, "profile_analysis", TaskConfig(model="example/profile"), None, "v1", "v1"
        )
    assert captured.value.code == "ai_cost_unknown"
    with Session(get_engine()) as db:
        assert db.get(InferenceCall, call_id).state == "unknown"


def test_partial_response_does_not_inherit_ui_defaults(transport: dict[str, Any]) -> None:
    identifier = configuration()
    transport["responses"] = [
        completion({"summary": "Synthetic partial"}),
        completion({"summary": "Synthetic partial"}),
    ]
    with pytest.raises(OperationError) as captured:
        provider.infer("profile_analysis", identifier, None, "Synthetic", {}, Facts)
    assert captured.value.code == "ai_schema"


def test_two_request_limit_is_shared_across_threads() -> None:
    identifier = configuration()

    def attempt() -> str:
        try:
            provider.reserve(
                identifier,
                "profile_analysis",
                TaskConfig(model="example/profile"),
                None,
                "v1",
                "v1",
            )
            return "reserved"
        except OperationError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: attempt(), range(4)))
    assert results.count("reserved") == 2 and results.count("ai_concurrency") == 2


def test_usage_shows_prior_day_unresolved_reservations(client: TestClient) -> None:
    identifier = configuration()
    call_id = provider.reserve(
        identifier, "profile_analysis", TaskConfig(model="example/profile"), None, "v1", "v1"
    )
    with Session(get_engine()) as db, db.begin():
        row = db.get(InferenceCall, call_id)
        row.created_at = now() - timedelta(days=1)
        row.state = "unknown"
    auth(client)
    response = client.get("/api/v1/settings/ai/usage").json()["tasks"][0]
    assert response["calls_today"] == 0 and response["unresolved_count"] == 1
    assert Decimal(response["held_usd"]) == Decimal(".56")


def test_contact_minimization_preserves_dates_and_line_boundaries() -> None:
    from app.domain.profile import Span
    from app.services.profiles import redacted_spans

    source = (
        "Nurse, 2020-01-01 - 2024-01-01\nEducator, 2015–2019\n"
        "Contact +44 7700 900123\nemail@example.test\n2011\n2012\n2013"
    )
    result = redacted_spans([Span(id="s1", text=source)])[0]
    assert "2020-01-01 - 2024-01-01" in result.text and "2015–2019" in result.text
    assert "2011\n2012\n2013" in result.text
    assert "+44" not in result.text and "email@example.test" not in result.text
    assert "[phone removed]" in result.text and "[email removed]" in result.text


def test_cancelled_operation_cannot_reserve_another_request() -> None:
    from app.services.operations import create_operation

    identifier = configuration()
    with Session(get_engine()) as db, db.begin():
        operation = create_operation(db, "profile_ingest", "cancel-test", {})
        operation.state = "cancelled"
        operation_id = operation.id
    with pytest.raises(OperationError) as captured:
        provider.reserve(
            identifier,
            "profile_analysis",
            TaskConfig(model="example/profile"),
            operation_id,
            "v1",
            "v1",
        )
    assert captured.value.code == "operation_cancelled"
    with Session(get_engine()) as db:
        assert db.scalar(select(InferenceCall)) is None


def test_verified_cost_requires_confirmation_and_does_not_retry(client: TestClient) -> None:
    identifier = configuration()
    call_id = provider.reserve(
        identifier, "profile_analysis", TaskConfig(model="example/profile"), None, "v1", "v1"
    )
    provider.finish(call_id, state="unknown", error_code="ai_transport")
    url = f"/api/v1/settings/ai/usage/{call_id}/verify"
    assert client.post(url, json={"cost_usd": "0"}).status_code == 401
    headers = auth(client)
    assert client.post(url, headers=headers, json={"cost_usd": "0"}).status_code == 422
    assert (
        client.post(
            url,
            headers=headers,
            json={"cost_usd": "-1", "confirmation": "I VERIFIED THE PROVIDER BILLING"},
        ).status_code
        == 422
    )
    response = client.post(
        url,
        headers=headers,
        json={"cost_usd": ".25", "confirmation": "I VERIFIED THE PROVIDER BILLING"},
    )
    assert response.status_code == 200
    assert response.json()["cost_source"] == "owner_verified"
    assert response.json()["reported_usd"] == "0.25"
    assert (
        client.post(
            url,
            headers=headers,
            json={"cost_usd": "0", "confirmation": "I VERIFIED THE PROVIDER BILLING"},
        ).status_code
        == 409
    )
    usage = client.get("/api/v1/settings/ai/usage").json()
    assert usage["unresolved"] == []
    assert Decimal(usage["tasks"][0]["reported_usd"]) == Decimal(".25")
    with Session(get_engine()) as db:
        assert len(list(db.scalars(select(InferenceCall)))) == 1
        assert db.scalar(select(Operation)) is None
    # The resolved reservation no longer pauses this task, but its cost still counts.
    provider.reserve(
        identifier, "profile_analysis", TaskConfig(model="example/profile"), None, "v1", "v1"
    )


def test_provider_reconciliation_records_provenance(transport: dict[str, Any]) -> None:
    identifier = configuration()
    transport["responses"] = [completion(usage={})]
    with pytest.raises(OperationError):
        run(identifier)
    with Session(get_engine()) as db:
        call_id = db.scalar(select(InferenceCall)).id
    reconcile_call(call_id)
    with Session(get_engine()) as db:
        row = db.get(InferenceCall, call_id)
        assert row.cost_source == "provider" and row.accounted_at is not None
        assert row.state == "reconciled"


# --- Decisions (Jev) adapter: Phase B mocked contract tests, no live traffic ---


def decision_configuration(revision: int = 1, **overrides: Any) -> UUID:
    config = TaskConfig(model="typesafe/jev-1.13", protocol="decisions", **overrides)
    with Session(get_engine()) as db, db.begin():
        row = TaskRevision(
            task="job_matching", revision=revision, config=config.model_dump(mode="json")
        )
        db.add(row)
        db.flush()
        return row.id


def decision_response(answers: dict[str, Any] | None = None, **overrides: Any) -> dict[str, Any]:
    return {
        "id": "gen-dec-synthetic",
        "model": "typesafe/jev-1.13-20260917",
        "provider": "TypeSafe",
        "answers": answers
        if answers is not None
        else {"probe": {"type": "choice", "choice": "ok", "confidence": 0.9}},
        "usage": {"input_tokens": 10, "output_tokens": 5, "cost": 0.00002},
        **overrides,
    }


def test_decisions_probe_contract_versioned_model_and_ledger(
    transport: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    identifier = decision_configuration()
    monkeypatch.setattr(get_settings(), "integration_mode", "live")
    monkeypatch.setattr(get_settings(), "decisions_live_enabled", True)
    transport["responses"] = [decision_response()]
    validate_task("job_matching", identifier, None)
    assert transport["urls"] == ["https://openrouter.ai/api/alpha/decisions"]
    request = transport["posts"][0]
    assert request["model"] == "typesafe/jev-1.13"
    assert request["provider"]["data_collection"] == "deny"
    assert request["provider"]["allow_fallbacks"] is True
    assert (
        not {"messages", "response_format", "max_tokens", "temperature", "reasoning"}
        & request.keys()
    )
    summary = RunLedger(get_settings().live_ledger_path).summary()
    assert summary["attempts"] == 1
    assert Decimal(summary["known_usd"]) == Decimal("0.00002")
    assert summary["unresolved_calls"] == []


def test_decisions_typed_contract_errors_are_terminal_without_repair(
    transport: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "integration_mode", "live")
    monkeypatch.setattr(get_settings(), "decisions_live_enabled", True)
    scenarios = [
        {},
        {"probe": {"type": "choice", "choice": "bogus"}},
        {"probe": {"type": "noul", "noul": 0.5}},
        {"probe": {"type": "noul", "noul": True}},
        {
            "probe": {
                "type": "choice",
                "choice": "ok",
                "probabilities": {"ok": 0.5},
            }
        },
        {
            "extra": {"type": "choice", "choice": "ok"},
            "probe": {"type": "choice", "choice": "ok"},
        },
    ]
    for index, answers in enumerate(scenarios, start=1):
        identifier = decision_configuration(revision=index)
        transport["responses"] = [decision_response(answers)]
        with pytest.raises(OperationError) as raised:
            validate_task("job_matching", identifier, None)
        assert raised.value.code == "ai_protocol", answers
    assert len(transport["posts"]) == len(scenarios)


def test_decisions_unknown_model_retains_billing_without_repair(
    transport: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    identifier = decision_configuration()
    monkeypatch.setattr(get_settings(), "integration_mode", "live")
    monkeypatch.setattr(get_settings(), "decisions_live_enabled", True)
    transport["responses"] = [decision_response(model="typesafe/other-1")]
    with pytest.raises(OperationError) as raised:
        validate_task("job_matching", identifier, None)
    assert raised.value.code == "ai_model_mismatch"
    assert len(transport["posts"]) == 1
    summary = RunLedger(get_settings().live_ledger_path).summary()
    assert Decimal(summary["known_usd"]) == Decimal("0.00002")


def test_decisions_missing_cost_blocks_and_holds(
    transport: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    identifier = decision_configuration()
    monkeypatch.setattr(get_settings(), "integration_mode", "live")
    monkeypatch.setattr(get_settings(), "decisions_live_enabled", True)
    transport["responses"] = [decision_response(usage={"input_tokens": 10, "output_tokens": 5})]
    with pytest.raises(OperationError) as raised:
        validate_task("job_matching", identifier, None)
    assert raised.value.code == "ai_cost_unknown"
    summary = RunLedger(get_settings().live_ledger_path).summary()
    assert Decimal(summary["held_usd"]) > 0
    with Session(get_engine()) as db:
        assert db.scalar(select(InferenceCall)).state == "unknown"


def test_decisions_transport_failure_sends_no_duplicate(
    transport: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    identifier = decision_configuration()
    monkeypatch.setattr(get_settings(), "integration_mode", "live")
    monkeypatch.setattr(get_settings(), "decisions_live_enabled", True)
    transport["responses"] = [httpx.ConnectError("synthetic failure")]
    with pytest.raises(OperationError) as raised:
        validate_task("job_matching", identifier, None)
    assert raised.value.code == "ai_transport"
    assert len(transport["posts"]) == 1
    summary = RunLedger(get_settings().live_ledger_path).summary()
    assert Decimal(summary["held_usd"]) > 0


def test_decisions_rate_limit_persists_cooldown(
    transport: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    identifier = decision_configuration()
    monkeypatch.setattr(get_settings(), "integration_mode", "live")
    monkeypatch.setattr(get_settings(), "decisions_live_enabled", True)
    transport["responses"] = [httpx.Response(429, headers={"Retry-After": "600"})]
    with pytest.raises(OperationError):
        validate_task("job_matching", identifier, None)
    assert len(transport["posts"]) == 1
    with Session(get_engine()) as db:
        row = db.get(TaskRevision, identifier)
        assert (
            row
            and row.cooldown_until is not None
            and row.cooldown_until > now() + timedelta(seconds=595)
        )


def test_matching_decisions_adapter_builds_validated_assessment() -> None:
    from app.ai.matching import decisions_adapter, evidence
    from app.domain.matching import category, validate
    from tests.synthetic_matching import FACTS, POSTINGS, PREFERENCES

    posting = POSTINGS[0]
    spans = evidence(FACTS, PREFERENCES, posting)
    answers = {
        "primary_function": ChoiceAnswer(choice="job:description"),
        "relation": ChoiceAnswer(choice="aligned"),
        "relevance_band": ScoreAnswer(score=2.0),
        "plausible_connection": NoulAnswer(noul=0.9),
    }
    assessment = decisions_adapter(FACTS, PREFERENCES, posting, spans).interpret(answers)
    assert assessment.relevance_score == 60 and assessment.relation == "aligned"
    assert assessment.plausible_connection is True
    assert any(item.span_id == "job:description" for item in assessment.function_evidence)
    validate(assessment, PREFERENCES, spans)
    assert category(assessment, PREFERENCES) == "possible_match"
    unclear = decisions_adapter(FACTS, PREFERENCES, posting, spans).interpret(
        {
            **answers,
            "relation": ChoiceAnswer(choice="insufficient"),
        }
    )
    assert unclear.relation == "unclear" and unclear.relevance_score is None
    duties_unknown = decisions_adapter(FACTS, PREFERENCES, posting, spans).interpret(
        {
            **answers,
            "primary_function": ChoiceAnswer(choice="insufficient"),
        }
    )
    assert duties_unknown.relation == "unclear" and duties_unknown.relevance_score is None
    with pytest.raises(ValueError):
        decisions_adapter(FACTS, PREFERENCES, posting, spans).interpret(
            {**answers, "primary_function": ChoiceAnswer(choice="preference:desired_roles")}
        )


def test_matching_decisions_preference_outcome_requires_selected_support() -> None:
    from uuid import uuid4

    from app.ai.matching import decisions_adapter, evidence
    from app.domain.matching import validate
    from app.domain.profile import Criterion, Preferences
    from tests.synthetic_matching import FACTS, POSTINGS

    criterion = Criterion(
        id=uuid4(), kind="other", description="London location", strength="required"
    )
    preferences = Preferences(desired_roles=["Strategy"], criteria=[criterion])
    posting = POSTINGS[0]
    spans = evidence(FACTS, preferences, posting)
    base = {
        "primary_function": ChoiceAnswer(choice="job:description"),
        "relation": ChoiceAnswer(choice="aligned"),
        "relevance_band": ScoreAnswer(score=2.0),
        "plausible_connection": NoulAnswer(noul=0.2),
        f"preference:{criterion.id}": ChoiceAnswer(choice="met"),
        f"preference:{criterion.id}:evidence": ChoiceAnswer(choice="insufficient"),
    }
    with pytest.raises(ValueError):
        decisions_adapter(FACTS, preferences, posting, spans).interpret(base)
    supported = {
        **base,
        f"preference:{criterion.id}:evidence": ChoiceAnswer(choice="job:description"),
    }
    assessment = decisions_adapter(FACTS, preferences, posting, spans).interpret(supported)
    validate(assessment, preferences, spans)


def test_chat_model_mismatch_is_terminal(
    transport: dict[str, Any],
) -> None:
    identifier = configuration()
    transport["responses"] = [completion(model="example/other")]
    with pytest.raises(OperationError) as raised:
        run(identifier)
    assert raised.value.code == "ai_model_mismatch"
    assert len(transport["posts"]) == 1


def test_decisions_protocol_restricted_to_matching(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    key = tmp_path / "key"
    key.write_text("synthetic-secret-never-returned")
    monkeypatch.setattr(get_settings(), "openrouter_key_file", key)
    headers = auth(client)
    headers = {**headers, "If-Match": '"0"'}
    body = {"task": "profile_analysis", "config": {"model": "example/x", "protocol": "decisions"}}
    assert client.patch("/api/v1/settings/ai", headers=headers, json=body).status_code == 422
    allowed = {
        "task": "job_matching",
        "config": {"model": "typesafe/jev-1.13", "protocol": "decisions"},
    }
    assert client.patch("/api/v1/settings/ai", headers=headers, json=allowed).status_code == 200


def test_assess_decisions_enforces_domain_validation_end_to_end(
    transport: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.synthetic_matching import FACTS, POSTINGS, PREFERENCES

    identifier = decision_configuration()
    monkeypatch.setattr(get_settings(), "integration_mode", "live")
    monkeypatch.setattr(get_settings(), "decisions_live_enabled", True)
    # The selection picks job duties evidence, but not job:description: the domain
    # validation the chat path enforces must reject it here too, with billing retained.
    transport["responses"] = [
        decision_response(
            {
                "primary_function": {"type": "choice", "choice": "job:title"},
                "relation": {"type": "choice", "choice": "aligned"},
                "relevance_band": {"type": "score", "score": 2.0},
                "plausible_connection": {"type": "noul", "noul": 0.9},
            }
        )
    ]
    from app.ai.matching import assess

    with pytest.raises(OperationError) as raised:
        assess(FACTS, PREFERENCES, POSTINGS[0], identifier, None)
    assert raised.value.code == "ai_schema"
    assert len(transport["posts"]) == 1
    with Session(get_engine()) as db:
        call = db.scalar(select(InferenceCall))
        assert call and call.state == "invalid" and call.reported_usd == Decimal("0.00002")


def test_decisions_live_dispatch_blocked_by_default(
    transport: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    identifier = decision_configuration()
    monkeypatch.setattr(get_settings(), "integration_mode", "live")
    transport["responses"] = [decision_response()]
    with pytest.raises(OperationError) as raised:
        validate_task("job_matching", identifier, None)
    assert raised.value.code == "ai_decisions_blocked"
    assert transport["posts"] == []
    with Session(get_engine()) as db:
        assert db.scalar(select(InferenceCall)) is None


def test_decisions_cumulative_cap_refuses_before_dispatch(
    transport: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    identifier = decision_configuration()
    monkeypatch.setattr(get_settings(), "integration_mode", "live")
    monkeypatch.setattr(get_settings(), "decisions_live_enabled", True)
    ledger = RunLedger(get_settings().live_ledger_path)
    for index in range(TOTAL_REQUESTS):
        ledger.admit(f"prefill-{index}", Decimal("0.001"))
        ledger.settle(f"prefill-{index}", Decimal(0))
    transport["responses"] = [decision_response()]
    with pytest.raises(OperationError) as raised:
        validate_task("job_matching", identifier, None)
    assert raised.value.code == "ai_budget"
    assert transport["posts"] == []


def test_ledger_concurrent_admission_cannot_overcount(tmp_path: Path) -> None:
    from concurrent.futures import ThreadPoolExecutor

    from app.ai.run_ledger import TOTAL_REQUESTS as cap

    ledger = RunLedger(tmp_path / "concurrency.json")

    def admit(index: int) -> str:
        try:
            ledger.admit(f"concurrent-{index}", Decimal("0.001"))
            return "admitted"
        except BudgetRefused:
            return "refused"

    with ThreadPoolExecutor(max_workers=4) as pool:
        outcomes = list(pool.map(admit, range(cap + 10)))
    assert outcomes.count("admitted") == cap
    assert outcomes.count("refused") == 10


# --- Launcher probe orchestration (run_probes): exercised offline before any paid run ---


def load_launcher() -> Any:
    import importlib.util

    path = Path(__file__).parents[2] / "scripts" / "validate-live-api.py"
    spec = importlib.util.spec_from_file_location("validate_live_api", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_run_probes_executes_luna_then_jev(
    transport: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    launcher = load_launcher()
    monkeypatch.setattr(get_settings(), "integration_mode", "live")
    monkeypatch.setattr(get_settings(), "decisions_live_enabled", True)
    transport["responses"] = [
        completion(model="openai/gpt-6-luna"),
        decision_response(),
    ]
    launcher.run_probes()
    assert transport["urls"] == [
        "https://openrouter.ai/api/v1/chat/completions",
        "https://openrouter.ai/api/alpha/decisions",
    ]
    with Session(get_engine()) as db:
        calls = list(db.scalars(select(InferenceCall).order_by(InferenceCall.created_at)))
        assert [call.state for call in calls] == ["succeeded", "succeeded"]
        revisions = list(db.scalars(select(TaskRevision)))
        assert sorted((revision.task, revision.revision) for revision in revisions) == [
            ("job_matching", 1),
            ("profile_analysis", 1),
        ]


def test_run_probes_stops_after_first_failure_without_jev_post(
    transport: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    launcher = load_launcher()
    monkeypatch.setattr(get_settings(), "integration_mode", "live")
    transport["responses"] = [httpx.Response(429, headers={"Retry-After": "600"})]
    with pytest.raises(SystemExit):
        launcher.run_probes()
    assert transport["urls"] == ["https://openrouter.ai/api/v1/chat/completions"]
    with Session(get_engine()) as db:
        assert db.scalar(select(InferenceCall)).state == "failed"
        revisions = list(db.scalars(select(TaskRevision)))
        assert [(revision.task, revision.revision) for revision in revisions] == [
            ("profile_analysis", 1)
        ]
