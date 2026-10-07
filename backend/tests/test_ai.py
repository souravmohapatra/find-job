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
from app.ai import provider
from app.ai.contracts import TaskConfig
from app.ai.models import AiLimitsRow, InferenceCall, TaskRevision
from app.ai.tasks import Probe, reconcile_call
from app.config import get_settings
from app.db import get_engine
from app.domain.profile import Evidence, Facts
from app.profile_models import Operation, now
from app.services.operations import OperationError, process_operation
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session


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
def transport(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    state: dict[str, Any] = {
        "posts": [],
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
