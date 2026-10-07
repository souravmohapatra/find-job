"""Assessment eligibility and scheduled snapshots; never performs network delivery."""

from datetime import datetime, time, timedelta
from typing import Any

from app.ai.configuration import latest
from app.collection.models import Company, Job, JobAssessment, JobRevision, Source
from app.config import get_settings
from app.domain.matching import POLICY_VERSION
from app.notifications.models import Digest, DigestItem, NotificationEvent, NotificationSettings
from app.notifications.schedule import next_slot
from app.profile_models import Operation, Profile, ProfileRevision, now
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, aliased


def record(db: Session, assessment: JobAssessment) -> None:
    """Caller persists assessment and event together under the shared profile lock."""
    if assessment.category not in {"match", "possible_match"}:
        return
    revision = db.get(JobRevision, assessment.job_revision_id)
    assert revision is not None
    job = db.get(Job, revision.job_id)
    assert job is not None
    prior = db.scalar(
        select(JobAssessment.id)
        .join(JobRevision, JobRevision.id == JobAssessment.job_revision_id)
        .where(
            JobRevision.job_id == job.id,
            JobAssessment.id != assessment.id,
            JobAssessment.integration_mode == assessment.integration_mode,
        )
        .limit(1)
    )
    db.add(
        NotificationEvent(
            assessment_id=assessment.id,
            job_id=job.id,
            kind="reassessment" if prior else "baseline" if job.baseline else "new",
            created_at=assessment.created_at,
        )
    )


def advance(settings: NotificationSettings, instant: datetime) -> None:
    slot = next_slot(instant, time.fromisoformat(settings.local_time), settings.timezone)
    settings.next_date, settings.next_due_at = slot.local_date, slot.at


def snapshot(db: Session, settings: NotificationSettings) -> Digest:
    assert settings.next_date is not None and settings.next_due_at is not None
    cutoff = settings.next_due_at
    profile = db.get(Profile, 1)
    profile_id = (
        db.scalar(
            select(ProfileRevision.id).where(ProfileRevision.revision == profile.current_revision)
        )
        if profile
        else None
    )
    config = latest(db, "job_matching")
    mode = get_settings().integration_mode
    previous_event = aliased(NotificationEvent)
    previous_assessment = aliased(JobAssessment)
    already_reserved_or_sent = (
        select(previous_event.id)
        .join(Digest, Digest.id == previous_event.digest_id)
        .join(previous_assessment, previous_assessment.id == previous_event.assessment_id)
        .where(
            previous_event.job_id == Job.id,
            previous_assessment.integration_mode == mode,
            Digest.state.in_(["pending", "sending", "sent", "unknown"]),
        )
        .correlate(Job)
        .exists()
    )
    rows = []
    if profile_id and config and config.config.get("model"):
        rows = list(
            db.execute(
                select(NotificationEvent, JobAssessment, JobRevision, Company)
                .join(JobAssessment, JobAssessment.id == NotificationEvent.assessment_id)
                .join(JobRevision, JobRevision.id == JobAssessment.job_revision_id)
                .join(Job, Job.id == JobRevision.job_id)
                .join(Company, Company.id == Job.company_id)
                .where(
                    NotificationEvent.digest_id.is_(None),
                    ~already_reserved_or_sent,
                    NotificationEvent.created_at <= cutoff,
                    JobAssessment.created_at <= cutoff,
                    JobAssessment.profile_revision_id == profile_id,
                    JobAssessment.config_id == config.id,
                    JobAssessment.policy_version == POLICY_VERSION,
                    JobAssessment.integration_mode == mode,
                    JobAssessment.category.in_(["match", "possible_match"]),
                    JobRevision.revision == Job.current_revision,
                    Job.availability != "closed",
                    Company.paused.is_(False),
                )
                .order_by(NotificationEvent.created_at, NotificationEvent.id)
            )
        )
    counts = {"new": 0, "baseline": 0, "reassessment": 0}
    companies: dict[str, dict[str, Any]] = {}
    examples: list[dict[str, Any]] = []
    for event, assessment, revision, company in rows:
        counts[event.kind] += 1
        company_counts = companies.setdefault(str(company.id), {"label": company.label, "count": 0})
        company_counts["count"] += 1
        if len(examples) < 10:
            examples.append(
                {
                    "job_id": str(revision.job_id),
                    "title": revision.posting["title"],
                    "company": company.label,
                    "kind": event.kind,
                    "category": assessment.category,
                }
            )
    source_errors = (
        db.scalar(
            select(func.count())
            .select_from(Source)
            .join(Company)
            .where(
                Source.enabled.is_(True), Company.paused.is_(False), Source.last_error.is_not(None)
            )
        )
        or 0
    )
    pending = (
        db.scalar(
            select(func.count())
            .select_from(Operation)
            .where(
                Operation.kind.in_(
                    ["source_collect", "job_extract", "job_assess", "discovery_step"]
                ),
                Operation.state.in_(["queued", "running"]),
            )
        )
        or 0
    )
    assessment_errors = 0
    matching_available = bool(profile_id and config and config.config.get("model"))
    if matching_available and config is not None:
        key = func.concat(
            "owner:job_assess:",
            JobRevision.id,
            ":",
            str(profile_id),
            ":",
            str(config.id),
            ":",
            POLICY_VERSION,
            ":",
            mode,
        )
        assessment_errors = (
            db.scalar(
                select(func.count())
                .select_from(Job)
                .join(
                    JobRevision,
                    (JobRevision.job_id == Job.id) & (JobRevision.revision == Job.current_revision),
                )
                .join(Company, Company.id == Job.company_id)
                .join(Operation, Operation.dedupe_key == key)
                .where(
                    Job.availability != "closed",
                    Company.paused.is_(False),
                    Operation.state.in_(["failed", "blocked"]),
                )
            )
            or 0
        )
    usable_source = (
        select(Source.id).where(Source.company_id == Company.id, Source.enabled.is_(True)).exists()
    )
    unresolved_companies = (
        db.scalar(
            select(func.count())
            .select_from(Company)
            .where(Company.paused.is_(False), ~usable_source)
        )
        or 0
    )
    needs_summary = bool(
        rows
        or settings.include_empty
        or source_errors
        or pending
        or assessment_errors
        or unresolved_companies
        or not matching_available
    )
    digest = Digest(
        local_date=settings.next_date,
        cutoff=cutoff,
        timezone=settings.timezone,
        local_time=settings.local_time,
        settings_revision=settings.revision,
        profile_revision_id=profile_id,
        integration_mode=mode,
        state="pending" if needs_summary else "skipped",
        snapshot={
            "counts": counts,
            "companies": companies,
            "examples": examples,
            "source_errors": source_errors,
            "pending_operations": pending,
            "assessment_errors": assessment_errors,
            "unresolved_companies": unresolved_companies,
            "matching_available": matching_available,
        },
    )
    db.add(digest)
    db.flush()
    for event, _, _, _ in rows:
        event.digest_id = digest.id
        db.add(DigestItem(digest_id=digest.id, event_id=event.id))
    return digest


def schedule(db: Session, instant: datetime | None = None) -> Digest | None:
    """A minute control tick snapshots once; missed slots wait for the next day."""
    instant = instant or now()
    db.execute(text("SELECT pg_advisory_xact_lock(1012001)"))
    settings = db.get(NotificationSettings, 1, with_for_update=True)
    if settings is None or not settings.enabled:
        return None
    if settings.next_due_at is None or settings.next_date is None:
        advance(settings, instant)
        return None
    if instant < settings.next_due_at:
        return None
    digest = None
    if instant - settings.next_due_at < timedelta(minutes=1):
        prior = db.scalar(select(Digest.id).where(Digest.local_date == settings.next_date))
        if prior is None:
            digest = snapshot(db, settings)
    advance(settings, instant)
    return digest
