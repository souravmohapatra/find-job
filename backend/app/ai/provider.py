"""OpenRouter structured inference; never log request/response bodies or credentials."""

import copy
import json
import re
import time
from collections.abc import Callable
from datetime import timedelta
from decimal import ROUND_CEILING, Decimal, InvalidOperation
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import quote
from uuid import UUID

import httpx
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.ai.configuration import limits, set_validation
from app.ai.contracts import TaskConfig, TaskKey
from app.ai.decisions import (
    DecisionsTask,
    normalize,
    parse_response,
)
from app.ai.decisions import (
    request_body as decisions_request_body,
)
from app.ai.models import InferenceCall, TaskRevision
from app.ai.run_ledger import BudgetRefused, RunLedger
from app.config import get_settings
from app.db import get_engine
from app.profile_models import Operation, now
from app.services.operations import OperationError

BASE_URL = "https://openrouter.ai/api/v1/"


def key_available() -> bool:
    try:
        return bool(get_settings().openrouter_key_file.read_text().strip())
    except OSError:
        return False


def client() -> httpx.Client:
    if get_settings().integration_mode != "live":
        raise OperationError(
            "mock_mode", "Live OpenRouter calls are disabled in mock mode.", blocked=True
        )
    try:
        key = get_settings().openrouter_key_file.read_text().strip()
        if not key:
            raise ValueError
    except (OSError, ValueError) as error:
        raise OperationError(
            "key_required", "Configure the server's OpenRouter key file.", blocked=True
        ) from error
    return httpx.Client(
        base_url=BASE_URL,
        headers={"Authorization": f"Bearer {key}"},
        timeout=20,
        follow_redirects=False,
    )


def strict_schema(model: type[BaseModel]) -> dict[str, Any]:
    schema = copy.deepcopy(model.model_json_schema())

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            value.pop("default", None)
            if value.get("type") == "object":
                value["additionalProperties"] = False
                value["required"] = list(value.get("properties", {}))
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(schema)
    return schema


def require_complete(value: Any, schema: dict[str, Any], root: dict[str, Any]) -> None:
    """Reject omitted fields locally even where the domain model has UI defaults."""
    if "$ref" in schema:
        schema = root["$defs"][schema["$ref"].rsplit("/", 1)[1]]
    if isinstance(value, dict):
        properties = schema.get("properties", {})
        if set(properties) != set(value):
            raise ValueError("Incomplete structured response")
        for key, child in value.items():
            require_complete(child, properties[key], root)
    elif isinstance(value, list):
        for child in value:
            require_complete(child, schema.get("items", {}), root)


def retry_delay(response: httpx.Response) -> int:
    value = response.headers.get("Retry-After", "")
    try:
        if value.isdigit():
            return max(1, int(value))
        return max(1, int((parsedate_to_datetime(value) - now()).total_seconds()))
    except (ValueError, TypeError, OverflowError):
        return 60


def http_failure(response: httpx.Response) -> OperationError:
    code = response.status_code
    if code == 401:
        return OperationError(
            "ai_authentication", "Check the server's OpenRouter API key.", blocked=True
        )
    if code == 402:
        return OperationError(
            "ai_credits",
            "OpenRouter credits are insufficient. Add credits before retrying.",
            blocked=True,
        )
    if code in {400, 403, 404, 422}:
        return OperationError(
            "ai_configuration",
            "The model, schema or routing restrictions are unavailable. Review"
            " AI settings and validate again.",
            blocked=True,
        )
    return OperationError(
        "ai_rate_limited" if code == 429 else "ai_unavailable",
        "OpenRouter is temporarily unavailable. The operation will retry within its limit.",
        retryable=code == 429 or code >= 500,
        retry_after=retry_delay(response),
    )


def money(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = Decimal(str(value))
        return result if result.is_finite() and Decimal(0) <= result <= Decimal("100000") else None
    except InvalidOperation:
        return None


CHARGE_KEYS = {
    "prompt",
    "completion",
    "request",
    "image",
    "web_search",
    "internal_reasoning",
    "input_cache_read",
    "input_cache_write",
}
# Documented pricing metadata that is not a per-request charge: discount is a rate
# reduction, overrides are tiered schedules (validated with the same bounds), and
# min_prompt_tokens is a volume threshold inside each override tier.
METADATA_KEYS = {"discount", "overrides", "min_prompt_tokens"}


def priced_within(pricing: Any, config: TaskConfig) -> bool:
    """True when a pricing schedule (base or one override tier) stays within ceilings.

    Uninterpretable values fail closed: the endpoint is skipped, never charged blind.
    """
    if not isinstance(pricing, dict):
        return False
    prompt, completion = money(pricing.get("prompt")), money(pricing.get("completion"))
    request = money(pricing.get("request", "0"))
    if prompt is None or completion is None or request is None:
        return False
    if (
        prompt * 1000000 > config.prompt_price
        or completion * 1000000 > config.completion_price
        or request > config.request_price
    ):
        return False
    if "discount" in pricing and money(pricing["discount"]) is None:
        return False
    # Text-only requests; unknown additional charges cannot be treated as zero.
    if any(
        money(value) != 0
        for key, value in pricing.items()
        if key not in CHARGE_KEYS | METADATA_KEYS
    ):
        return False
    if money(pricing.get("internal_reasoning", "0")) not in {Decimal(0), completion}:
        return False
    cached_prices = [
        money(pricing.get(key, "0")) for key in ("input_cache_read", "input_cache_write")
    ]
    if any(
        price is None or price * 1000000 > config.prompt_price for price in cached_prices
    ):
        return False
    return True


def endpoint_tags(http: httpx.Client, config: TaskConfig) -> list[str]:
    """Recheck each model at dispatch; require a priced, capable endpoint for every fallback."""
    tags: set[str] = set()
    required = {"response_format", "structured_outputs"}
    if config.temperature is not None:
        required.add("temperature")
    if config.reasoning_effort:
        required.add("reasoning")
    for model in [config.model, *config.fallback_models]:
        assert model
        try:
            response = http.get(f"models/{quote(model, safe='/')}/endpoints")
            if response.status_code != 200:
                raise http_failure(response)
            endpoints = response.json()["data"]["endpoints"]
            compatible: set[str] = set()
            for endpoint in endpoints:
                tag = endpoint.get("tag")
                if not isinstance(tag, str) or not required.issubset(
                    endpoint.get("supported_parameters", [])
                ):
                    continue
                if config.providers and not any(
                    tag == p or tag.startswith(p + "/") for p in config.providers
                ):
                    continue
                if (
                    int(endpoint.get("context_length") or 0)
                    < config.input_tokens + config.output_tokens
                ):
                    continue
                if (
                    int(endpoint.get("max_completion_tokens") or config.output_tokens)
                    < config.output_tokens
                ):
                    continue
                if (
                    int(endpoint.get("max_prompt_tokens") or config.input_tokens)
                    < config.input_tokens
                ):
                    continue
                pricing = endpoint.get("pricing", {})
                if not priced_within(pricing, config):
                    continue
                # Tiered schedules price the same request differently by volume; every
                # documented tier must also respect the configured ceilings.
                overrides = pricing.get("overrides") or []
                if not isinstance(overrides, list) or any(
                    not isinstance(tier, dict) or not priced_within(tier, config)
                    for tier in overrides
                ):
                    continue
                compatible.add(tag)
            if not compatible:
                raise OperationError(
                    "ai_capability",
                    "No priced endpoint supports this model's structured output, token"
                    " limits and selected parameters. Review AI settings.",
                    blocked=True,
                )
            tags.update(compatible)
        except (ValueError, KeyError, TypeError) as error:
            raise OperationError(
                "ai_catalog_invalid",
                "OpenRouter endpoint metadata could not be validated.",
                blocked=True,
            ) from error
    return sorted(tags)


def estimate_bound(config: TaskConfig) -> Decimal:
    """Upper bound on one request's cost, shared by the database and run ledgers."""
    estimate = (
        Decimal(config.input_tokens) * config.prompt_price
        + Decimal(config.output_tokens) * config.completion_price
    ) / 1000000 + config.request_price
    return estimate.quantize(Decimal("0.00000001"), rounding=ROUND_CEILING)


def recover_reservations() -> None:
    # Separate transaction: retain the interrupted-call state even when new work is blocked.
    with Session(get_engine()) as db, db.begin():
        db.execute(text("SELECT pg_advisory_xact_lock(1012003)"))
        # A crash after reserving might have sent a billable request. Never reclaim as free.
        stale = db.scalars(
            select(InferenceCall).where(
                InferenceCall.state == "reserved",
                InferenceCall.created_at < now() - timedelta(minutes=5),
            )
        )
        for row in stale:
            row.state = "unknown"
            row.error_code = "ai_interrupted"
        db.flush()


def reserve(
    config_id: UUID,
    task: TaskKey,
    config: TaskConfig,
    operation_id: UUID | None,
    prompt_version: str,
    schema_version: str,
) -> UUID:
    recover_reservations()
    estimate = estimate_bound(config)
    with Session(get_engine()) as db, db.begin():
        db.execute(text("SELECT pg_advisory_xact_lock(1012003)"))
        if operation_id is not None:
            operation = db.get(Operation, operation_id)
            if operation is None or operation.state != "running":
                raise OperationError(
                    "operation_cancelled",
                    "This operation is no longer running. No further AI request was sent.",
                    blocked=True,
                )
        _, budget = limits(db)
        unknown = db.scalar(
            select(InferenceCall.id)
            .where(InferenceCall.task == task, InferenceCall.state == "unknown")
            .limit(1)
        )
        if unknown:
            raise OperationError(
                "ai_cost_unknown",
                "An earlier request has unresolved billing. Reconcile usage before"
                " retrying this task.",
                blocked=True,
            )
        active = (
            db.scalar(
                select(func.count())
                .select_from(InferenceCall)
                .where(InferenceCall.state == "reserved")
            )
            or 0
        )
        if active >= 2:
            raise OperationError(
                "ai_concurrency",
                "Waiting for an available AI request slot.",
                retryable=True,
                retry_after=30,
            )
        start = now().replace(hour=0, minute=0, second=0, microsecond=0)
        calls = (
            db.scalar(
                select(func.count())
                .select_from(InferenceCall)
                .where(InferenceCall.created_at >= start)
            )
            or 0
        )
        charged = db.scalar(
            select(
                func.coalesce(
                    func.sum(func.coalesce(InferenceCall.reported_usd, InferenceCall.reserved_usd)),
                    0,
                )
            ).where(
                (InferenceCall.created_at >= start)
                | (InferenceCall.state.in_(["reserved", "unknown"]))
            )
        ) or Decimal(0)
        if calls >= budget.daily_calls or charged + estimate > budget.daily_usd:
            raise OperationError(
                "ai_budget",
                "The daily AI call or estimated spend limit is reached. Review "
                "usage or wait for the next UTC day.",
                blocked=True,
            )
        row = InferenceCall(
            config_id=config_id,
            task=task,
            operation_id=operation_id,
            requested_model=config.model or "",
            prompt_version=prompt_version,
            schema_version=schema_version,
            reserved_usd=estimate,
        )
        db.add(row)
        db.flush()
        return row.id


def finish(
    call_id: UUID,
    *,
    state: str,
    error_code: str | None = None,
    response: dict[str, Any] | None = None,
    latency: int = 0,
    cost_source: str = "provider",
) -> None:
    response = response or {}
    usage = response.get("usage")
    usage = usage if isinstance(usage, dict) else {}
    cost = money(usage.get("cost"))
    with Session(get_engine()) as db, db.begin():
        row = db.get(InferenceCall, call_id, with_for_update=True)
        assert row
        row.state = state if cost is not None else "unknown"
        row.error_code = error_code
        row.reported_usd = cost
        row.cost_source = cost_source if cost is not None else None
        row.accounted_at = now() if cost is not None else None
        row.latency_ms = latency
        row.finished_at = now()
        for field, key in [
            ("generation_id", "id"),
            ("returned_model", "model"),
            ("provider", "provider"),
        ]:
            value = response.get(key)
            if isinstance(value, str) and len(value) <= 200:
                setattr(row, field, value)
        for field in ["prompt_tokens", "completion_tokens"]:
            value = usage.get(field)
            if isinstance(value, int) and not isinstance(value, bool) and 0 <= value < 10000000:
                setattr(row, field, value)


def stored_protocol(config_id: UUID, task: TaskKey) -> str:
    """The stored revision's wire protocol; unknown configurations keep the chat default."""
    with Session(get_engine()) as db:
        revision = db.get(TaskRevision, config_id)
        if revision is None or revision.task != task:
            return "chat"
        return TaskConfig.model_validate(revision.config).protocol


def settle_ledger(ledger: RunLedger | None, call_id: UUID, response: dict[str, Any] | None) -> None:
    """Mirror a finished call's provider-reported cost into the cumulative run ledger.

    A missing cost keeps the call's bound held; the ledger never treats an unknown
    outcome as free.
    """
    if ledger is None:
        return
    usage = (response or {}).get("usage")
    ledger.settle(str(call_id), money(usage.get("cost")) if isinstance(usage, dict) else None)


DECISIONS_URL = "https://openrouter.ai/api/alpha/decisions"
# Decisions responses may return a dated concrete version of the requested model
# (for example typesafe/jev-1.13-20260917); the exact-prefix digit-suffix rule covers
# only that documented form. No broad prefix acceptance.
DECISIONS_VERSION_PATTERN = re.compile(r"^\d{8}$")


def dispatch_decisions(
    task: TaskKey,
    config_id: UUID,
    operation_id: UUID | None,
    config: TaskConfig,
    task_input: DecisionsTask,
    prompt_version: str,
    schema_version: str,
) -> Any:
    """Single-attempt Decisions dispatch through the shared reservation and ledger gates.

    typed-contract errors are terminal: the protocol has no chat-style repair, so a
    failure retains the paid attempt and stops instead of re-sending.
    """
    if not get_settings().decisions_live_enabled:
        raise OperationError(
            "ai_decisions_blocked",
            "Live Decisions dispatch is disabled: the protocol has no demonstrated "
            "per-request billing bound. Review the validation plan with the owner.",
            blocked=True,
        )
    assert config.model
    bound = (
        len(
            json.dumps(
                {"state": task_input.state, "questions": task_input.questions},
                ensure_ascii=False,
                default=str,
            ).encode()
        )
        + 1024
    )
    if bound > config.input_tokens:
        raise OperationError(
            "ai_input_too_large",
            "The complete state and questions exceed the configured input limit.",
            blocked=True,
        )
    settings = get_settings()
    ledger = RunLedger(settings.live_ledger_path) if settings.integration_mode == "live" else None
    body = decisions_request_body(
        config.model,
        task_input.state,
        task_input.questions,
        {
            # Documented Decisions ProviderPreferences only; chat-only fields such as
            # require_parameters and endpoint "only" tags are not blindly sent.
            "data_collection": "deny",
            "zdr": config.zdr,
            "allow_fallbacks": True,
            "max_price": {
                "prompt": float(config.prompt_price),
                "completion": float(config.completion_price),
                "request": float(config.request_price),
            },
        },
    )
    with client() as http:
        call_id = reserve(config_id, task, config, operation_id, prompt_version, schema_version)
        if ledger is not None:
            # The Decisions protocol has no provider-side output-token bound (no
            # max_tokens field), so unlike chat the estimate is not a demonstrated
            # ceiling. Reserving the entire remaining allowance prevents multi-call
            # under-counting but does NOT bound a single response's actual charge;
            # live Decisions dispatch stays blocked pending an owner decision on a
            # demonstrated per-request bound (see PROGRESS.md).
            try:
                ledger.admit(str(call_id), ledger.remaining_usd())
            except (BudgetRefused, ValueError) as refused:
                reason = getattr(refused, "reason", "spend_limit")
                finish(
                    call_id,
                    state="failed",
                    error_code=f"ai_budget_{reason}",
                    response={"usage": {"cost": 0}},
                    cost_source="rejected",
                )
                raise OperationError(
                    "ai_budget",
                    "The cumulative live-validation budget cap is reached. Reconcile "
                    "the run ledger before any further request.",
                    blocked=True,
                ) from refused
        started = time.monotonic()
        try:
            # Absolute URL: joining "alpha/decisions" to the /api/v1/ base would
            # target the wrong endpoint.
            response = http.post(DECISIONS_URL, json=body, timeout=config.timeout_seconds)
        except httpx.HTTPError as error:
            settle_ledger(ledger, call_id, None)
            finish(call_id, state="unknown", error_code="ai_transport")
            raise OperationError(
                "ai_transport",
                "The request outcome and cost are uncertain. Its reservation is "
                "retained; reconcile usage before retrying.",
                blocked=True,
            ) from error
        latency = int((time.monotonic() - started) * 1000)
        if response.status_code != 200:
            failure = http_failure(response)
            known_free = response.status_code in {400, 401, 402, 403, 404, 422, 429}
            settle_ledger(ledger, call_id, {"usage": {"cost": 0}} if known_free else None)
            finish(
                call_id,
                state="failed",
                error_code=failure.code,
                response={"usage": {"cost": 0}} if known_free else None,
                cost_source="rejected",
                latency=latency,
            )
            if response.status_code == 429:
                with Session(get_engine()) as db, db.begin():
                    row = db.get(TaskRevision, config_id, with_for_update=True)
                    assert row
                    row.cooldown_until = now() + timedelta(seconds=failure.retry_after or 60)
            if failure.blocked:
                set_validation(config_id, "blocked", failure.code)
            raise failure
        try:
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError
        except ValueError as error:
            settle_ledger(ledger, call_id, None)
            finish(call_id, state="unknown", error_code="ai_response_invalid", latency=latency)
            raise OperationError(
                "ai_response_invalid",
                "The provider response was unreadable; the billing reservation is retained.",
                blocked=True,
            ) from error
        try:
            parsed = parse_response(data)
            normalize(task_input.questions, parsed)
        except ValueError as error:
            # A typed-contract error never receives a chat repair prompt.
            settle_ledger(ledger, call_id, data)
            finish(
                call_id, state="invalid", error_code="ai_protocol", response=data, latency=latency
            )
            raise OperationError(
                "ai_protocol",
                "The Decisions response did not satisfy the typed question contract.",
                blocked=True,
            ) from error
        returned = parsed.model
        allowed_models = {
            model.removesuffix(":free") for model in [config.model, *config.fallback_models]
        }
        allowed_models.update([config.model, *config.fallback_models])
        if returned not in allowed_models and not any(
            returned.startswith(f"{model}-")
            and DECISIONS_VERSION_PATTERN.fullmatch(returned[len(model) + 1 :])
            for model in allowed_models
        ):
            settle_ledger(ledger, call_id, data)
            finish(
                call_id,
                state="invalid",
                error_code="ai_model_mismatch",
                response=data,
                latency=latency,
            )
            raise OperationError(
                "ai_model_mismatch",
                "The provider returned an unrequested model. Review the model "
                "configuration before retrying.",
                blocked=True,
            )
        settle_ledger(ledger, call_id, data)
        finish(call_id, state="completed", response=data, latency=latency)
        if parsed.usage.cost is None:
            raise OperationError(
                "ai_cost_unknown",
                "The provider omitted request cost. Reconcile usage before continuing.",
                blocked=True,
            )
        try:
            result = task_input.interpret(parsed.answers)
        except ValueError as error:
            finish(call_id, state="invalid", error_code="ai_schema", response=data, latency=latency)
            raise OperationError(
                "ai_schema",
                "The decision outcome failed evidence validation. Review the task inputs.",
                blocked=True,
            ) from error
        finish(call_id, state="succeeded", response=data, latency=latency)
        set_validation(config_id, "validated")
        return result


def infer[T: BaseModel](
    task: TaskKey,
    config_id: UUID | None,
    operation_id: UUID | None,
    system: str,
    payload: object,
    output: type[T],
    validate: Callable[[T], None] | None = None,
    *,
    prompt_version: str = "v1",
    schema_version: str = "v1",
    validation_probe: bool = False,
    decisions: "DecisionsTask | None" = None,
) -> T:
    if config_id is None:
        raise OperationError(
            "configuration_required",
            "Choose and validate a model for this task in Settings.",
            blocked=True,
        )
    with Session(get_engine()) as db:
        revision = db.get(TaskRevision, config_id)
        if revision is None or revision.task != task:
            raise OperationError(
                "configuration_required",
                "This task's saved model configuration is unavailable.",
                blocked=True,
            )
        if revision.cooldown_until and revision.cooldown_until > now():
            raise OperationError(
                "ai_rate_limited",
                "This model is cooling down after a provider rate limit.",
                retryable=True,
                retry_after=int((revision.cooldown_until - now()).total_seconds()) + 1,
            )
        if revision.validation_state == "blocked" and not validation_probe:
            raise OperationError(
                revision.error_code or "ai_configuration",
                "This configuration is paused. Review AI Settings and run validation "
                "before retrying.",
                blocked=True,
            )
        config = TaskConfig.model_validate(revision.config)
    if not config.model:
        raise OperationError(
            "configuration_required", "Choose a model for this task in Settings.", blocked=True
        )
    schema = strict_schema(output)
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]
    # UTF-8 bytes are deliberately conservative for supported byte/subword tokenizers;
    # include schema and framing allowance. Do not silently truncate private documents.
    input_bound = (
        len(json.dumps({"messages": messages, "schema": schema}, ensure_ascii=False).encode())
        + 1024
    )
    if input_bound > config.input_tokens:
        raise OperationError(
            "ai_input_too_large",
            "This input cannot be processed completely within the model's "
            "configured input limit. Increase the limit or supply a shorter "
            "document.",
            blocked=True,
        )
    settings = get_settings()
    if settings.integration_mode == "mock" and settings.mock_ai_dir is not None:
        from app.ai.fixtures import replay

        return replay(
            task, config.model, system, payload, output, validate, prompt_version, schema_version
        )
    if settings.integration_mode == "live" and config.model.startswith("mock/"):
        raise OperationError(
            "mock_model", "Choose a real model before enabling live inference.", blocked=True
        )
    # Cumulative cap across processes and restarts; active only for billable traffic.
    ledger = RunLedger(settings.live_ledger_path) if settings.integration_mode == "live" else None
    if config.protocol == "decisions":
        if task != "job_matching":
            raise OperationError(
                "ai_protocol",
                "The Decisions protocol is supported only for job matching.",
                blocked=True,
            )
        if decisions is None:
            raise OperationError(
                "ai_protocol",
                "This revision uses the Decisions protocol and requires typed questions.",
                blocked=True,
            )
        result: T = dispatch_decisions(
            task, config_id, operation_id, config, decisions, prompt_version, schema_version
        )
        return result
    if decisions is not None:
        raise OperationError(
            "ai_protocol",
            "This revision uses the chat protocol; Decisions input is not accepted.",
            blocked=True,
        )
    with client() as http:
        try:
            tags = endpoint_tags(http, config)
        except httpx.HTTPError as error:
            raise OperationError(
                "ai_catalog_unavailable",
                "OpenRouter capabilities could not be checked. Try again later.",
                retryable=True,
            ) from error
        except OperationError as error:
            set_validation(config_id, "blocked", error.code)
            raise
        provider: dict[str, Any] = {
            "require_parameters": True,
            "data_collection": "deny",
            "zdr": config.zdr,
            "only": tags,
            "allow_fallbacks": True,
            "max_price": {
                "prompt": float(config.prompt_price),
                "completion": float(config.completion_price),
                "request": float(config.request_price),
            },
        }
        body: dict[str, Any] = {
            "model": config.model,
            "messages": messages,
            "stream": False,
            "max_tokens": config.output_tokens,
            "provider": provider,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": output.__name__, "strict": True, "schema": schema},
            },
        }
        if config.fallback_models:
            body["models"] = [config.model, *config.fallback_models]
        if config.temperature is not None:
            body["temperature"] = config.temperature
        if config.reasoning_effort:
            body["reasoning"] = {"effort": config.reasoning_effort}
        for attempt in range(2):
            call_id = reserve(config_id, task, config, operation_id, prompt_version, schema_version)
            if ledger is not None:
                try:
                    ledger.admit(str(call_id), estimate_bound(config))
                except BudgetRefused as refused:
                    # No request was sent, so the call is genuinely free.
                    finish(
                        call_id,
                        state="failed",
                        error_code=f"ai_budget_{refused.reason}",
                        response={"usage": {"cost": 0}},
                        cost_source="rejected",
                    )
                    raise OperationError(
                        "ai_budget",
                        "The cumulative live-validation budget cap is reached. Reconcile "
                        "the run ledger before any further request.",
                        blocked=True,
                    ) from refused
            started = time.monotonic()
            try:
                response = http.post("chat/completions", json=body, timeout=config.timeout_seconds)
            except httpx.HTTPError as error:
                settle_ledger(ledger, call_id, None)
                finish(call_id, state="unknown", error_code="ai_transport")
                raise OperationError(
                    "ai_transport",
                    "The request outcome and cost are uncertain. Its reservation is "
                    "retained; reconcile usage before retrying.",
                    blocked=True,
                ) from error
            latency = int((time.monotonic() - started) * 1000)
            if response.status_code != 200:
                failure = http_failure(response)
                # Explicit input/auth/rate rejections are free; server errors remain ambiguous.
                known_free = response.status_code in {400, 401, 402, 403, 404, 422, 429}
                settle_ledger(ledger, call_id, {"usage": {"cost": 0}} if known_free else None)
                finish(
                    call_id,
                    state="failed",
                    error_code=failure.code,
                    response={"usage": {"cost": 0}} if known_free else None,
                    cost_source="rejected",
                    latency=latency,
                )
                if response.status_code == 429:
                    with Session(get_engine()) as db, db.begin():
                        row = db.get(TaskRevision, config_id, with_for_update=True)
                        assert row
                        row.cooldown_until = now() + timedelta(seconds=failure.retry_after or 60)
                if failure.blocked:
                    set_validation(config_id, "blocked", failure.code)
                raise failure
            try:
                data = response.json()
                if not isinstance(data, dict):
                    raise ValueError
            except ValueError as error:
                settle_ledger(ledger, call_id, None)
                finish(call_id, state="unknown", error_code="ai_response_invalid", latency=latency)
                raise OperationError(
                    "ai_response_invalid",
                    "The provider response was unreadable; the billing reservation is retained.",
                    blocked=True,
                ) from error
            settle_ledger(ledger, call_id, data)
            finish(call_id, state="completed", response=data, latency=latency)
            if (
                money(
                    data.get("usage", {}).get("cost")
                    if isinstance(data.get("usage"), dict)
                    else None
                )
                is None
            ):
                raise OperationError(
                    "ai_cost_unknown",
                    "The provider omitted request cost. Reconcile usage before continuing.",
                    blocked=True,
                )
            allowed_models = {
                model.removesuffix(":free") for model in [config.model, *config.fallback_models]
            }
            allowed_models.update([config.model, *config.fallback_models])
            if data.get("model") not in allowed_models:
                # Model mismatch is not a repairable syntax error: reject visibly and
                # retain billing instead of re-sending an unrequested-model request.
                finish(
                    call_id,
                    state="invalid",
                    error_code="ai_model_mismatch",
                    response=data,
                    latency=latency,
                )
                raise OperationError(
                    "ai_model_mismatch",
                    "The provider returned an unrequested model. Review the model "
                    "configuration before retrying.",
                    blocked=True,
                )
            try:
                choice = data["choices"][0]
                if choice.get("finish_reason") != "stop":
                    raise ValueError("Incomplete response")
                parsed = json.loads(choice["message"]["content"])
                require_complete(parsed, schema, schema)
                result = output.model_validate(parsed)
                if validate:
                    validate(result)
            except (ValueError, KeyError, IndexError, TypeError) as error:
                settle_ledger(ledger, call_id, data)
                finish(
                    call_id, state="invalid", error_code="ai_schema", response=data, latency=latency
                )
                if attempt == 1:
                    raise OperationError(
                        "ai_schema",
                        "The model returned invalid or unsupported facts twice. Review the"
                        " model configuration before retrying.",
                    ) from error
                # Re-run the same complete input; do not include private invalid output/errors.
                body["messages"] = [
                    *messages,
                    {
                        "role": "system",
                        "content": "The previous response failed schema or evidence validation. "
                        "Return a complete schema-valid answer using only evidence in the "
                        "supplied input.",
                    },
                ]
                if input_bound + 300 > config.input_tokens:
                    raise OperationError(
                        "ai_input_too_large",
                        "There is insufficient input capacity for a complete repair request.",
                        blocked=True,
                    ) from error
                continue
            settle_ledger(ledger, call_id, data)
            finish(call_id, state="succeeded", response=data, latency=latency)
            set_validation(config_id, "validated")
            return result
    raise AssertionError("Inference loop exhausted")
