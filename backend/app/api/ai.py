"""Authenticated model configuration. Saving settings never sends a paid request."""

from typing import Any
from uuid import UUID, uuid4

from app.ai.configuration import latest, limits
from app.ai.contracts import (
    TASKS,
    AiLimits,
    AiSettingsView,
    CallView,
    TaskConfig,
    TaskUpdate,
    UsageView,
    ValidateRequest,
    VerifyCost,
)
from app.ai.models import AiLimitsRow, InferenceCall, TaskRevision
from app.ai.provider import key_available
from app.api.contracts import OperationAccepted
from app.api.profiles import Expected, Key
from app.auth import DB, Auth
from app.config import get_settings
from app.domain.matching import POLICY_VERSION
from app.errors import problem
from app.profile_models import now
from app.services.operations import create_operation, operation_response
from fastapi import APIRouter, Response
from sqlalchemy import func, select, text

router = APIRouter(prefix="/settings/ai", tags=["settings"])


def check_revision(expected: str | None, current: int) -> None:
    if expected is None:
        raise problem(428, "revision_required", "Reload Settings before saving.")
    if expected != f'"{current}"':
        raise problem(
            409,
            "revision_conflict",
            "These settings changed elsewhere. Your edits have not been saved.",
        )


@router.get("", response_model=AiSettingsView)
def get_ai(session: Auth, db: DB) -> dict[str, Any]:
    revision, budget = limits(db)
    tasks = []
    for task in TASKS:
        row = latest(db, task)
        tasks.append(
            {
                "task": task,
                "revision": row.revision if row else 0,
                "config": row.config if row else TaskConfig().model_dump(mode="json"),
                "validation_state": row.validation_state if row else "configuration_required",
                "error_code": row.error_code if row else None,
            }
        )
    return {
        "integration_mode": get_settings().integration_mode,
        "key_configured": key_available(),
        "limits_revision": revision,
        "limits": budget,
        "tasks": tasks,
    }


@router.patch("", response_model=AiSettingsView)
def update_ai(
    body: TaskUpdate, session: Auth, db: DB, response: Response, if_match: Expected = None
) -> dict[str, Any]:
    db.execute(text("SELECT pg_advisory_xact_lock(1012004)"))
    previous = latest(db, body.task)
    revision = previous.revision if previous else 0
    check_revision(if_match, revision)
    row = TaskRevision(
        task=body.task,
        revision=revision + 1,
        config=body.config.model_dump(mode="json"),
        validation_state="unvalidated" if body.config.model else "configuration_required",
    )
    db.add(row)
    db.flush()
    if body.task == "job_matching":
        create_operation(
            db,
            "profile_reassess",
            f"ai:{row.id}",
            {
                "ai_config_id": str(row.id),
                "reason": "model_changed",
                "integration_mode": get_settings().integration_mode,
                "policy_version": POLICY_VERSION,
            },
        )
    db.commit()
    response.headers["ETag"] = f'"{row.revision}"'
    return get_ai(session, db)


@router.patch("/limits", response_model=AiSettingsView)
def update_limits(
    body: AiLimits, session: Auth, db: DB, if_match: Expected = None
) -> dict[str, Any]:
    db.execute(text("SELECT pg_advisory_xact_lock(1012003)"))
    revision, _ = limits(db)
    check_revision(if_match, revision)
    row = db.get(AiLimitsRow, 1)
    if row is None:
        row = AiLimitsRow(id=1, settings={})
        db.add(row)
    row.settings = body.model_dump(mode="json")
    row.revision = revision + 1
    db.commit()
    return get_ai(session, db)


@router.post("/validate", status_code=202, response_model=OperationAccepted)
def validate_config(
    body: ValidateRequest, session: Auth, db: DB, idempotency_key: Key = None
) -> dict[str, str]:
    row = latest(db, body.task)
    if row is None or not row.config.get("model"):
        raise problem(422, "configuration_required", "Choose a model before validation.")
    if get_settings().integration_mode == "live" and not body.acknowledge_cost:
        raise problem(
            422,
            "cost_confirmation_required",
            "Confirm the synthetic validation request may incur API cost.",
        )
    operation = create_operation(
        db,
        "ai_validate",
        idempotency_key or str(uuid4()),
        {"task": body.task, "config_id": str(row.id)},
    )
    db.commit()
    return operation_response(operation, row.id)


@router.get("/usage", response_model=UsageView)
def get_usage(session: Auth, db: DB) -> dict[str, Any]:
    start = now().replace(hour=0, minute=0, second=0, microsecond=0)
    summary = []
    for task in TASKS:
        rows = list(
            db.scalars(
                select(InferenceCall).where(
                    InferenceCall.task == task, InferenceCall.created_at >= start
                )
            )
        )
        summary.append(
            {
                "task": task,
                "calls_today": len(rows),
                "reported_usd": str(sum(row.reported_usd or 0 for row in rows)),
                "held_usd": str(
                    db.scalar(
                        select(func.coalesce(func.sum(InferenceCall.reserved_usd), 0)).where(
                            InferenceCall.task == task, InferenceCall.reported_usd.is_(None)
                        )
                    )
                    or 0
                ),
                "unresolved_count": db.scalar(
                    select(func.count())
                    .select_from(InferenceCall)
                    .where(InferenceCall.task == task, InferenceCall.state == "unknown")
                ),
            }
        )
    recent = db.scalars(select(InferenceCall).order_by(InferenceCall.created_at.desc()).limit(50))
    return {
        "day_start_utc": start,
        "tasks": summary,
        "recent": [call_data(row) for row in recent],
        "unresolved": [
            call_data(row)
            for row in db.scalars(
                select(InferenceCall)
                .where(InferenceCall.state == "unknown")
                .order_by(InferenceCall.created_at)
                .limit(100)
            )
        ],
    }


def call_data(row: InferenceCall) -> dict[str, Any]:
    return {
        "id": row.id,
        "task": row.task,
        "operation_id": row.operation_id,
        "state": row.state,
        "model": row.returned_model or row.requested_model,
        "provider": row.provider,
        "generation_id": row.generation_id,
        "reserved_usd": row.reserved_usd,
        "reported_usd": row.reported_usd,
        "cost_source": row.cost_source,
        "accounted_at": row.accounted_at,
        "error_code": row.error_code,
        "created_at": row.created_at,
    }


@router.post("/usage/{call_id}/verify", response_model=CallView)
def verify_cost(call_id: UUID, body: VerifyCost, session: Auth, db: DB) -> dict[str, Any]:
    db.execute(text("SELECT pg_advisory_xact_lock(1012003)"))
    call = db.get(InferenceCall, call_id, with_for_update=True)
    if call is None:
        raise problem(404, "call_not_found", "This request could not be found.")
    if call.state != "unknown":
        raise problem(
            409,
            "billing_changed",
            "This request is no longer unresolved. Refresh usage before continuing.",
        )
    call.reported_usd = body.cost_usd
    call.cost_source = "owner_verified"
    call.accounted_at = now()
    call.state = "owner_reconciled"
    db.commit()
    return call_data(call)


@router.post("/usage/{call_id}/reconcile", status_code=202, response_model=OperationAccepted)
def reconcile_usage(
    call_id: UUID, session: Auth, db: DB, idempotency_key: Key = None
) -> dict[str, str]:
    call = db.get(InferenceCall, call_id)
    if call is None:
        raise problem(404, "call_not_found", "This request could not be found.")
    if call.state != "unknown" or not call.generation_id:
        raise problem(
            409,
            "reconciliation_unavailable",
            "Automatic reconciliation requires an unresolved request with a "
            "generation ID. Keep its reservation until billing can be "
            "verified.",
        )
    operation = create_operation(
        db, "ai_reconcile", idempotency_key or str(uuid4()), {"call_id": str(call_id)}
    )
    db.commit()
    return operation_response(operation, call_id)


@router.get("/models")
def get_models(session: Auth) -> dict[str, Any]:
    from app.ai.catalog import models
    from app.services.operations import OperationError

    try:
        return {"models": models(), "integration_mode": get_settings().integration_mode}
    except OperationError as error:
        raise problem(503, error.code, error.message) from error
