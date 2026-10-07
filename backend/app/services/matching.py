"""Version-bound assessment preparation and bounded reassessment fan-out."""

from typing import Any
from uuid import UUID

from app.ai.configuration import capture
from app.ai.matching import assess, evidence
from app.collection.contracts import Posting
from app.collection.models import Job, JobAssessment, JobRevision
from app.config import get_settings
from app.db import get_engine
from app.domain.matching import POLICY_VERSION, Assessment, category, validate
from app.domain.profile import Facts, Preferences
from app.profile_models import Profile, ProfileRevision
from app.services.operations import OperationError, create_operation
from sqlalchemy import select
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
        create_operation(
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
