import base64
import json
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from app.ai.configuration import capture
from app.ai.models import TaskRevision
from app.api.contracts import OperationAccepted, OperationView
from app.api.inventory_contracts import (
    AssessmentView,
    Availability,
    FeedbackInput,
    FeedbackView,
    JobDetail,
    JobPage,
    JobView,
)
from app.auth import DB, Auth
from app.collection.models import (
    Company,
    Job,
    JobAssessment,
    JobFeedback,
    JobRevision,
    JobSource,
    Source,
)
from app.config import get_settings
from app.domain.matching import POLICY_VERSION
from app.errors import problem
from app.profile_models import Operation, Profile, ProfileRevision, now
from app.services.operations import create_operation, operation_response, request_hash
from fastapi import APIRouter, Header, Query
from sqlalchemy import ColumnElement, func, select, text, tuple_
from sqlalchemy.orm import Session

router = APIRouter(prefix="/jobs", tags=["jobs"])
Key = Annotated[str | None, Header(alias="Idempotency-Key", max_length=128)]


def matching_context(db: Session) -> tuple[UUID | None, UUID | None, str]:
    profile_id = db.scalar(
        select(ProfileRevision.id)
        .join(
            Profile,
            (Profile.id == ProfileRevision.profile_id)
            & (Profile.current_revision == ProfileRevision.revision),
        )
        .where(Profile.id == 1)
    )
    config = capture(db, "job_matching")
    return profile_id, UUID(config) if config else None, get_settings().integration_mode


def matching_ready(db: Session, context: tuple[UUID | None, UUID | None, str]) -> bool:
    profile_id, config_id, _ = context
    config = db.get(TaskRevision, config_id) if config_id else None
    return bool(profile_id and config and config.config.get("model"))


def assessment_conditions(
    context: tuple[UUID | None, UUID | None, str],
) -> tuple[ColumnElement[bool], ...]:
    profile_id, config_id, mode = context
    return (
        JobAssessment.profile_revision_id == profile_id,
        JobAssessment.config_id == config_id,
        JobAssessment.policy_version == POLICY_VERSION,
        JobAssessment.integration_mode == mode,
    )


def enrich(
    db: Session, items: list[JobView], context: tuple[UUID | None, UUID | None, str]
) -> None:
    if not items:
        return
    ids = [item.revision_id for item in items]
    current = {
        row.job_revision_id: row
        for row in db.scalars(
            select(JobAssessment).where(
                JobAssessment.job_revision_id.in_(ids), *assessment_conditions(context)
            )
        )
    }
    historical = set(
        db.scalars(
            select(JobRevision.job_id)
            .join(JobAssessment, JobAssessment.job_revision_id == JobRevision.id)
            .where(JobRevision.job_id.in_([item.id for item in items]))
            .distinct()
        )
    )
    profile_id, config_id, mode = context
    operations: dict[str, Operation] = {}
    if profile_id:
        statement = select(Operation).where(
            Operation.kind == "job_assess",
            Operation.parameters["job_revision_id"].astext.in_(
                [str(identifier) for identifier in ids]
            ),
            Operation.parameters["profile_revision_id"].astext == str(profile_id),
            Operation.parameters["policy_version"].astext == POLICY_VERSION,
            Operation.parameters["integration_mode"].astext == mode,
        )
        config_field = Operation.parameters["config_id"].astext
        statement = statement.where(
            config_field == str(config_id) if config_id else config_field.is_(None)
        )
        for operation in db.scalars(
            statement.order_by(Operation.created_at.desc(), Operation.id.desc())
        ):
            operations.setdefault(operation.parameters["job_revision_id"], operation)
    for item in items:
        row = current.get(item.revision_id)
        if row:
            item.assessment_status = "assessed"
            item.assessment = AssessmentView.model_validate(row)
        elif item.id in historical:
            item.assessment_status = "stale"
        pending = operations.get(str(item.revision_id))
        if pending:
            item.assessment_operation = OperationView.model_validate(pending, from_attributes=True)


def job_view(job: Job, revision: JobRevision, label: str) -> JobView:
    return JobView(
        id=job.id,
        company_id=job.company_id,
        company_label=label,
        revision_id=revision.id,
        revision=revision.revision,
        availability=job.availability,
        baseline=job.baseline,
        first_seen_at=job.first_seen_at,
        last_seen_at=job.last_seen_at,
        posting=revision.posting,
    )


@router.get("", response_model=JobPage)
def jobs(
    session: Auth,
    db: DB,
    company_id: UUID | None = None,
    view: Literal["all", "recommended"] = "recommended",
    availability: Availability = "open",
    q: str = Query("", max_length=200),
    limit: int = Query(30, ge=1, le=100),
    cursor: str | None = Query(None, max_length=1000),
) -> JobPage:
    context = matching_context(db)
    available = matching_ready(db, context)
    if view == "recommended" and not available:
        raise problem(
            503,
            "matching_unavailable",
            "Review a profile and configure a matching model to enable shortlisting. "
            "Browse all collected jobs.",
        )
    statement = (
        select(Job, JobRevision, Company.label)
        .join(
            JobRevision,
            (JobRevision.job_id == Job.id) & (JobRevision.revision == Job.current_revision),
        )
        .join(Company, Company.id == Job.company_id)
    )
    if view == "recommended":
        statement = statement.join(
            JobAssessment, JobAssessment.job_revision_id == JobRevision.id
        ).where(
            *assessment_conditions(context), JobAssessment.category.in_(["match", "possible_match"])
        )
    if company_id:
        if db.get(Company, company_id) is None:
            raise problem(404, "company_not_found", "This company watch could not be found.")
        statement = statement.where(Job.company_id == company_id)
    if availability == "open":
        statement = statement.where(Job.availability.in_(["active", "unknown"]))
    elif availability != "all":
        statement = statement.where(Job.availability == availability)
    if q.strip():
        document = func.concat_ws(
            " ",
            Company.label,
            JobRevision.posting["title"].astext,
            JobRevision.posting["description"].astext,
        )
        statement = statement.where(
            func.to_tsvector("simple", document).op("@@")(
                func.plainto_tsquery("simple", q.strip()),
            )
        )
    filters = request_hash([company_id, availability, q.strip(), view, context, POLICY_VERSION])
    if cursor:
        try:
            payload = json.loads(base64.urlsafe_b64decode(cursor))
            timestamp = datetime.fromisoformat(payload["seen"])
            identifier = UUID(payload["id"])
            if payload["filters"] != filters or timestamp.tzinfo is None:
                raise ValueError
        except (ValueError, KeyError, TypeError):
            raise problem(
                422, "invalid_cursor", "Reload the list after changing its filters."
            ) from None
        statement = statement.where(
            tuple_(Job.first_seen_at, Job.id) < tuple_(timestamp, identifier)
        )
    rows = db.execute(
        statement.order_by(Job.first_seen_at.desc(), Job.id.desc()).limit(limit + 1)
    ).all()
    items = [job_view(job, revision, label) for job, revision, label in rows[:limit]]
    enrich(db, items, context)
    next_cursor = None
    if len(rows) > limit:
        last = items[-1]
        next_cursor = base64.urlsafe_b64encode(
            json.dumps(
                {
                    "seen": last.first_seen_at.isoformat(),
                    "id": str(last.id),
                    "filters": filters,
                }
            ).encode()
        ).decode()
    return JobPage(items=items, next_cursor=next_cursor, matching_available=available)


@router.get("/{identifier}", response_model=JobDetail)
def job_detail(identifier: UUID, session: Auth, db: DB) -> JobDetail:
    row = db.execute(
        select(Job, JobRevision, Company.label)
        .join(
            JobRevision,
            (JobRevision.job_id == Job.id) & (JobRevision.revision == Job.current_revision),
        )
        .join(Company, Company.id == Job.company_id)
        .where(Job.id == identifier)
    ).first()
    if row is None:
        raise problem(404, "job_not_found", "This collected job could not be found.")
    job, revision, label = row
    sources = list(
        db.scalars(
            select(Source)
            .join(JobSource, JobSource.source_id == Source.id)
            .where(JobSource.job_id == identifier)
            .distinct()
            .order_by(Source.id)
        )
    )
    item = job_view(job, revision, label)
    enrich(db, [item], matching_context(db))
    return JobDetail(
        **item.model_dump(),
        sources=sources,
        revision_count=job.current_revision,
        feedback=(
            FeedbackView.model_validate(feedback)
            if (feedback := db.get(JobFeedback, identifier))
            else None
        ),
    )


@router.post("/{identifier}/reassess", response_model=OperationAccepted, status_code=202)
def reassess(
    identifier: UUID, session: Auth, db: DB, idempotency_key: Key = None
) -> dict[str, str]:
    from app.collection.inventory import assess_intent

    db.execute(text("SELECT pg_advisory_xact_lock(1012001)"))
    job = db.get(Job, identifier)
    if job is None:
        raise problem(404, "job_not_found", "This collected job could not be found.")
    receipt = (
        create_operation(db, "job_reassess_request", idempotency_key, {"job_id": str(identifier)})
        if idempotency_key
        else None
    )
    if receipt and receipt.state == "succeeded":
        previous = db.get(Operation, UUID(receipt.parameters["assessment_operation_id"]))
        assert previous is not None
        response = operation_response(previous, identifier)
        db.commit()
        return response
    context = matching_context(db)
    if not matching_ready(db, context):
        raise problem(
            409, "matching_unavailable", "Review a profile and configure a matching model first."
        )
    revision = db.scalar(
        select(JobRevision).where(
            JobRevision.job_id == identifier, JobRevision.revision == job.current_revision
        )
    )
    assert revision is not None
    operation = assess_intent(db, job, revision)
    assert operation is not None
    # Reuse successful/current or pending work. Explicit requests may retry a terminal failure.
    if operation.state in {"failed", "blocked", "cancelled"}:
        operation.state = "queued"
        operation.attempts = 0
        operation.available_at = now()
        operation.dispatched_at = operation.finished_at = operation.lease_until = None
        operation.lease_token = None
        operation.error_code = operation.error_message = None
        operation.progress = "Waiting to reassess"
    if receipt:
        receipt.parameters = {**receipt.parameters, "assessment_operation_id": str(operation.id)}
        receipt.state = "succeeded"
        receipt.finished_at = now()
        receipt.progress = "Assessment request recorded"
    response = operation_response(operation, identifier)
    db.commit()
    return response


@router.put("/{identifier}/feedback", response_model=FeedbackView)
def feedback(identifier: UUID, body: FeedbackInput, session: Auth, db: DB) -> FeedbackView:
    # Coordinate profile purge and serialize first insert as well as edits.
    db.execute(text("SELECT pg_advisory_xact_lock(1012001)"))
    if db.get(Job, identifier) is None:
        raise problem(404, "job_not_found", "This collected job could not be found.")
    row = db.get(JobFeedback, identifier)
    version = row.revision if row else 0
    if version != body.expected_revision:
        raise problem(
            409,
            "feedback_conflict",
            "Feedback changed elsewhere. Reload the saved feedback before saving your edits.",
        )
    if row is None:
        row = JobFeedback(job_id=identifier)
        db.add(row)
    row.value, row.reason = body.value, body.reason
    row.revision, row.updated_at = version + 1, now()
    db.flush()
    result = FeedbackView.model_validate(row)
    db.commit()
    return result
