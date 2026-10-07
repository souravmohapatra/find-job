"""Version-bound assessment preparation and bounded reassessment fan-out."""

from typing import Any
from uuid import UUID

from app.ai.configuration import capture, latest
from app.ai.matching import assess, evidence
from app.collection.contracts import Posting
from app.collection.models import Job, JobAssessment, JobRevision
from app.config import get_settings
from app.db import get_engine
from app.domain.matching import POLICY_VERSION, Assessment, category, validate
from app.domain.profile import Facts, Preferences
from app.profile_models import Operation, Profile, ProfileRevision
from app.services.operations import OperationError, create_operation
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session


def saved(db: Session, parameters: dict[str, Any]) -> JobAssessment | None:
    return db.scalar(
        select(JobAssessment).where(
            JobAssessment.job_revision_id == UUID(parameters["job_revision_id"]),
            JobAssessment.profile_revision_id == UUID(parameters["profile_revision_id"]),
            JobAssessment.config_id == UUID(parameters["config_id"]),
            JobAssessment.policy_version == parameters.get("policy_version", POLICY_VERSION),
            JobAssessment.integration_mode == parameters.get("integration_mode", "mock"),
        )
    )


def prepare(parameters: dict[str, Any], operation_id: UUID) -> Assessment:
    if parameters.get("integration_mode", "mock") != get_settings().integration_mode:
        raise OperationError(
            "assessment_mode_changed",
            "Reassess this job in the current integration mode.",
            blocked=True,
        )
    if parameters.get("policy_version", POLICY_VERSION) != POLICY_VERSION:
        raise OperationError(
            "assessment_policy_changed", "Reassess this job with the current policy."
        )
    if not parameters.get("config_id"):
        raise OperationError(
            "configuration_required", "Choose a matching model in Settings.", blocked=True
        )
    with Session(get_engine()) as db:
        profile = db.get(ProfileRevision, UUID(parameters["profile_revision_id"]))
        revision = db.get(JobRevision, UUID(parameters["job_revision_id"]))
        if profile is None or revision is None or str(revision.job_id) != parameters["job_id"]:
            raise OperationError(
                "assessment_snapshot_missing", "This assessment's source revision is unavailable."
            )
        prior = saved(db, parameters)
        if prior:
            return Assessment.model_validate(prior.report)
        facts = Facts.model_validate(profile.facts)
        preferences = Preferences.model_validate(profile.preferences)
        posting = Posting.model_validate(revision.posting)
    return assess(facts, preferences, posting, UUID(parameters["config_id"]), operation_id)


def save(db: Session, parameters: dict[str, Any], operation_id: UUID, report: Assessment) -> None:
    # Operation lease and shared profile/purge lock are held by the caller.
    profile = db.get(ProfileRevision, UUID(parameters["profile_revision_id"]))
    revision = db.get(JobRevision, UUID(parameters["job_revision_id"]))
    if profile is None or revision is None or saved(db, parameters):
        return
    facts = Facts.model_validate(profile.facts)
    preferences = Preferences.model_validate(profile.preferences)
    posting = Posting.model_validate(revision.posting)
    validate(report, preferences, evidence(facts, preferences, posting))
    db.add(
        JobAssessment(
            job_revision_id=revision.id,
            profile_revision_id=profile.id,
            config_id=UUID(parameters["config_id"]),
            policy_version=POLICY_VERSION,
            integration_mode=parameters.get("integration_mode", "mock"),
            category=category(report, preferences),
            report=report.model_dump(mode="json"),
            operation_id=operation_id,
        )
    )


def expand(db: Session, parameters: dict[str, Any], batch_size: int = 100) -> int:
    if parameters.get("policy_version", POLICY_VERSION) != POLICY_VERSION:
        raise OperationError("assessment_policy_changed", "Reassessment uses an outdated policy.")
    profile = db.get(Profile, 1)
    revision = (
        db.scalar(
            select(ProfileRevision).where(ProfileRevision.revision == profile.current_revision)
        )
        if profile
        else None
    )
    if revision is None or (
        parameters.get("profile_revision_id")
        and parameters["profile_revision_id"] != str(revision.id)
    ):
        return 0
    if parameters.get("integration_mode", "mock") != get_settings().integration_mode:
        raise OperationError(
            "assessment_mode_changed",
            "Request reassessment in the current integration mode.",
            blocked=True,
        )
    config_id = (
        parameters["ai_config_id"] if "ai_config_id" in parameters else capture(db, "job_matching")
    )
    statement = (
        select(Job, JobRevision)
        .join(
            JobRevision,
            (JobRevision.job_id == Job.id) & (JobRevision.revision == Job.current_revision),
        )
        .where(Job.availability != "closed")
    )
    if parameters.get("after_job_id"):
        statement = statement.where(Job.id > UUID(parameters["after_job_id"]))
    rows = db.execute(statement.order_by(Job.id).limit(batch_size + 1)).all()
    for job, job_revision in rows[:batch_size]:
        enqueue(db, job, job_revision, revision, config_id)
    if len(rows) > batch_size:
        after = str(rows[batch_size - 1][0].id)
        create_operation(
            db,
            "profile_reassess",
            f"batch:{revision.id}:{config_id}:{after}:{POLICY_VERSION}:{get_settings().integration_mode}",
            {
                "profile_revision_id": str(revision.id),
                "ai_config_id": config_id,
                "after_job_id": after,
                "policy_version": POLICY_VERSION,
                "integration_mode": get_settings().integration_mode,
            },
        )
    return min(len(rows), batch_size)


def current(db: Session, job_revision_id: UUID) -> JobAssessment | None:
    profile = db.get(Profile, 1)
    revision_id = (
        db.scalar(
            select(ProfileRevision.id).where(ProfileRevision.revision == profile.current_revision)
        )
        if profile
        else None
    )
    config_id = capture(db, "job_matching")
    if revision_id is None or config_id is None:
        return None
    return db.scalar(
        select(JobAssessment).where(
            JobAssessment.job_revision_id == job_revision_id,
            JobAssessment.profile_revision_id == revision_id,
            JobAssessment.config_id == UUID(config_id),
            JobAssessment.policy_version == POLICY_VERSION,
            JobAssessment.integration_mode == get_settings().integration_mode,
        )
    )


def enqueue(
    db: Session,
    job: Job,
    job_revision: JobRevision,
    revision: ProfileRevision,
    config_id: str | None,
) -> Operation:
    return create_operation(
        db,
        "job_assess",
        f"{job_revision.id}:{revision.id}:{config_id}:{POLICY_VERSION}:{get_settings().integration_mode}",
        {
            "job_id": str(job.id),
            "job_revision_id": str(job_revision.id),
            "profile_revision_id": str(revision.id),
            "config_id": config_id,
            "policy_version": POLICY_VERSION,
            "integration_mode": get_settings().integration_mode,
        },
    )


def reconcile(db: Session, batch_size: int = 100) -> int:
    """Queue missing current intents, including upgrades/rollbacks, without retrying failures."""
    if not 1 <= batch_size <= 100:
        raise ValueError("Use a reconciliation batch of 1–100 jobs.")
    db.execute(text("SELECT pg_advisory_xact_lock(1012001)"))
    profile = db.get(Profile, 1)
    revision = (
        db.scalar(
            select(ProfileRevision).where(
                ProfileRevision.profile_id == 1,
                ProfileRevision.revision == profile.current_revision,
            )
        )
        if profile
        else None
    )
    config = latest(db, "job_matching")
    if revision is None or config is None or not config.config.get("model"):
        return 0
    config_id = str(config.id)
    key = func.concat(
        "owner:job_assess:",
        JobRevision.id,
        ":",
        str(revision.id),
        ":",
        config_id,
        ":",
        POLICY_VERSION,
        ":",
        get_settings().integration_mode,
    )
    known = select(Operation.id).where(Operation.dedupe_key == key).exists()
    rows = db.execute(
        select(Job, JobRevision)
        .join(
            JobRevision,
            (JobRevision.job_id == Job.id) & (JobRevision.revision == Job.current_revision),
        )
        .where(Job.availability != "closed", ~known)
        .order_by(Job.id)
        .limit(batch_size)
    ).all()
    for job, job_revision in rows:
        enqueue(db, job, job_revision, revision, config_id)
    return len(rows)
