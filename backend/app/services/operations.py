import hashlib
import json
from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

from app.db import get_engine
from app.errors import problem
from app.profile_models import Operation, now
from sqlalchemy import select, text
from sqlalchemy.orm import Session


class OperationError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        blocked: bool = False,
        retryable: bool = False,
        retry_after: int | None = None,
    ):
        self.code = code
        self.message = message
        self.blocked = blocked
        self.retryable = retryable
        self.retry_after = retry_after
        super().__init__(message)


def request_hash(data: object) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()


def create_operation(
    db: Session, kind: str, key: str, parameters: dict[str, Any], fingerprint: str | None = None
) -> Operation:
    # Scope keys by operation kind/owner (the database currently has exactly one owner).
    dedupe = f"owner:{kind}:{key}"
    if len(dedupe) > 200:
        raise problem(
            422, "invalid_idempotency_key", "Use an idempotency key of at most 128 characters."
        )
    db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": dedupe})
    digest = fingerprint or request_hash(parameters)
    existing = db.scalar(select(Operation).where(Operation.dedupe_key == dedupe))
    if existing:
        if existing.request_hash != digest:
            raise problem(
                409,
                "idempotency_conflict",
                "This request key was already used for different input.",
            )
        return existing
    operation = Operation(kind=kind, dedupe_key=dedupe, request_hash=digest, parameters=parameters)
    db.add(operation)
    db.flush()
    return operation


def operation_response(operation: Operation, resource_id: UUID) -> dict[str, str]:
    return {
        "operation_id": str(operation.id),
        "resource_id": str(resource_id),
        "status_url": f"/api/v1/operations/{operation.id}",
    }


def process_operation(operation_id: UUID) -> None:
    token = uuid4()
    with Session(get_engine()) as db, db.begin():
        # A queue entry can be consumed before dispatch commits its intent-row lock.
        # Skipping that row would falsely acknowledge the queue job without claiming work.
        # Bound the wait; a longer database stall leaves the durable intent for recovery.
        db.execute(text("SET LOCAL lock_timeout = '10s'"))
        operation = db.scalar(
            select(Operation).where(Operation.id == operation_id).with_for_update()
        )
        if operation is None or operation.state in {"succeeded", "failed", "blocked", "cancelled"}:
            return
        if operation.available_at > now():
            return
        if operation.state == "running" and operation.lease_until and operation.lease_until > now():
            return
        operation.state = "running"
        operation.lease_token = token
        operation.lease_until = now() + timedelta(minutes=10)
        operation.attempts += 1
        operation.progress = "Processing"
        kind = operation.kind
        parameters = dict(operation.parameters)
    try:
        if kind == "profile_ingest":
            from app.services.profiles import analyze_document

            result = analyze_document(UUID(parameters["document_id"]), operation_id, parameters)
        elif kind in {"company_check", "company_discover", "profile_reassess"}:
            pass  # Fan-out is committed with completion after the lease is checked.
        elif kind == "job_assess":
            from app.services.matching import prepare as prepare_assessment

            assessment_result = prepare_assessment(parameters, operation_id)
        elif kind == "discovery_step":
            from app.collection.discovery import prepare

            discovery_result = prepare(UUID(parameters["run_id"]), parameters["cursor"])
        elif kind == "source_collect":
            from app.collection.runner import prepare_page

            page_result = prepare_page(UUID(parameters["run_id"]), parameters["offset"])
        elif kind == "ai_validate":
            from app.ai.tasks import validate_task

            validate_task(parameters["task"], UUID(parameters["config_id"]), operation_id)
        elif kind == "ai_reconcile":
            from app.ai.tasks import reconcile_call

            reconcile_call(UUID(parameters["call_id"]))
        else:
            raise OperationError(
                "handler_pending",
                "This task is not available in this development build.",
                blocked=True,
            )
        with Session(get_engine()) as db, db.begin():
            db.execute(text("SELECT pg_advisory_xact_lock(1012001)"))
            operation = db.get(Operation, operation_id, with_for_update=True)
            if operation is None or operation.lease_token != token or operation.state != "running":
                return
            if kind == "profile_ingest":
                from app.services.profiles import save_analysis

                save_analysis(db, UUID(parameters["document_id"]), result)
            check_progress = None
            if kind == "job_assess":
                from app.services.matching import save

                save(db, parameters, operation_id, assessment_result)
            if kind == "profile_reassess":
                from app.services.matching import expand

                count = expand(db, parameters)
                check_progress = f"{count} job assessments queued or already pending."
            if kind == "company_discover":
                from app.collection.discovery import begin
                from app.collection.models import Company

                company = db.get(Company, UUID(parameters["company_id"]), with_for_update=True)
                pending = begin(db, company) if company else None
                check_progress = (
                    "Discovery queued or already pending."
                    if pending
                    else "Discovery needs a website, or the company is paused."
                )
            if kind == "discovery_step":
                from app.collection.discovery import apply

                apply(db, UUID(parameters["run_id"]), parameters["cursor"], discovery_result)
            if kind == "company_check":
                from app.collection.inventory import begin_run
                from app.collection.models import Company, Source

                company = db.get(Company, UUID(parameters["company_id"]), with_for_update=True)
                if company is None or company.paused:
                    check_progress = "Company is paused or unavailable. No checks started."
                else:
                    sources = list(
                        db.scalars(
                            select(Source)
                            .where(Source.company_id == company.id)
                            .order_by(Source.id)
                            .with_for_update()
                        )
                    )
                    count = sum(begin_run(db, source) is not None for source in sources)
                    check_progress = f"{count} source checks queued or already pending."
                    if not sources:
                        check_progress = "No source is configured. Discover or add a job source."
            if kind == "source_collect":
                from app.collection.inventory import apply_page

                apply_page(
                    db, UUID(parameters["run_id"]), parameters["offset"], page_result, operation_id
                )
            operation.state = "succeeded"
            operation.progress = check_progress or (
                "Ready for review" if kind == "profile_ingest" else "Completed"
            )
            operation.finished_at = now()
            operation.lease_until = None
            operation.error_code = operation.error_message = None
    except Exception as error:
        failure = (
            error
            if isinstance(error, OperationError)
            else OperationError(
                "processing_failed",
                "Processing failed. Retry the operation or upload a readable document.",
            )
        )
        with Session(get_engine()) as db, db.begin():
            db.execute(text("SELECT pg_advisory_xact_lock(1012001)"))
            operation = db.get(Operation, operation_id, with_for_update=True)
            if operation is None or operation.lease_token != token or operation.state != "running":
                return
            operation.state = "blocked" if failure.blocked else "failed"
            if failure.retryable and operation.attempts < 3:
                operation.state = "queued"
                operation.available_at = now() + timedelta(
                    seconds=max(30 * 2**operation.attempts, failure.retry_after or 0)
                )
            operation.error_code, operation.error_message = failure.code, failure.message
            if kind == "profile_ingest":
                from app.profile_models import Document, ProfileDraft

                document = db.get(Document, UUID(parameters["document_id"]))
                draft = db.scalar(
                    select(ProfileDraft).where(
                        ProfileDraft.document_id == UUID(parameters["document_id"])
                    )
                )
                if document and document.deleted_at is None:
                    document.status = operation.state
                if draft and draft.status != "activated":
                    draft.status = "processing" if operation.state == "queued" else operation.state
            if kind == "source_collect":
                from app.collection.runner import record_failure

                record_failure(
                    db,
                    UUID(parameters["run_id"]),
                    failure.code,
                    terminal=operation.state != "queued",
                    retry_after=failure.retry_after,
                )
            if kind == "discovery_step" and operation.state != "queued":
                from app.collection.discovery import DiscoveryResult, apply

                apply(
                    db,
                    UUID(parameters["run_id"]),
                    parameters["cursor"],
                    DiscoveryResult(issues=[failure.code]),
                )
            operation.progress = failure.message
            operation.lease_until = None
            operation.dispatched_at = None
