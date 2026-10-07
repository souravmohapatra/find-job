"""Transactional inventory epochs. Only complete authoritative runs reconcile omissions."""

import hashlib
from datetime import timedelta
from uuid import UUID

from app.ai.configuration import capture
from app.collection.contracts import InventoryPage
from app.collection.models import (
    CollectionPage,
    CollectionRun,
    Company,
    Job,
    JobRevision,
    JobSource,
    Observation,
    PageExtraction,
    Source,
)
from app.profile_models import Operation, Profile, ProfileRevision, now
from app.services.operations import create_operation
from sqlalchemy import select
from sqlalchemy.orm import Session


def key(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def page_operation(db: Session, run: CollectionRun) -> Operation:
    snapshot = db.get(PageExtraction, (run.id, run.next_offset))
    if snapshot:
        operation = db.get(Operation, snapshot.operation_id)
        assert operation is not None
        return operation
    return create_operation(
        db,
        "source_collect",
        f"{run.id}:{run.next_offset}",
        {"run_id": str(run.id), "offset": run.next_offset},
    )


def begin_run(db: Session, source: Source) -> Operation | None:
    """Caller locks the source. Repeated checks join the current page operation."""
    clock = now()
    if not source.enabled or (source.cooldown_until and source.cooldown_until > clock):
        return None
    company = db.get(Company, source.company_id)
    if company is None or company.paused:
        return None
    active = db.scalar(
        select(CollectionRun)
        .where(CollectionRun.source_id == source.id, CollectionRun.state == "collecting")
        .with_for_update()
    )
    if active:
        if (
            active.started_at > clock - timedelta(hours=24)
            and active.source_revision == source.revision
        ):
            return page_operation(db, active)
        active.state = "expired"
        active.finished_at = clock
        active.issues = [*active.issues, "epoch_expired_or_source_changed"]
    run = CollectionRun(
        source_id=source.id,
        source_revision=source.revision,
        frontier=[source.url] if source.adapter == "generic_http" else [],
    )
    db.add(run)
    db.flush()
    # Stable 0–59 second jitter spreads watches without replaying downtime intervals.
    source.next_due_at = clock + timedelta(hours=source.interval_hours, seconds=source.id.int % 60)
    return page_operation(db, run)


def schedule_due(db: Session, limit: int = 100) -> int:
    sources = db.scalars(
        select(Source)
        .join(Company, Company.id == Source.company_id)
        .where(Source.enabled, ~Company.paused, Source.next_due_at <= now())
        .order_by(Source.next_due_at, Source.id)
        .with_for_update(of=Source, skip_locked=True)
        .limit(limit)
    )
    return sum(begin_run(db, source) is not None for source in sources)


def update_availability(db: Session, job: Job) -> None:
    associations = list(db.scalars(select(JobSource).where(JobSource.job_id == job.id)))
    job.availability = "active" if any(row.available for row in associations) else "closed"


def assess_intent(db: Session, job: Job, revision: JobRevision) -> Operation | None:
    profile = db.get(Profile, 1)
    approved = (
        db.scalar(
            select(ProfileRevision).where(ProfileRevision.revision == profile.current_revision)
        )
        if profile
        else None
    )
    if approved is None:
        return None  # A later profile activation expands the full inventory for assessment.
    config_id = capture(db, "job_matching")
    from app.services.matching import enqueue

    return enqueue(db, job, revision, approved, config_id)


def apply_page(
    db: Session, run_id: UUID, offset: int, page: InventoryPage, operation_id: UUID
) -> None:
    """Caller verifies the operation lease, then commits this with operation completion."""
    initial = db.get(CollectionRun, run_id)
    if initial is None:
        return
    initial_source = db.get(Source, initial.source_id)
    assert initial_source is not None
    # Serialize cross-source canonical merges within a company, then source/run mutations.
    company = db.get(Company, initial_source.company_id, with_for_update=True)
    source = db.get(Source, initial.source_id, with_for_update=True, populate_existing=True)
    run = db.get(CollectionRun, run_id, with_for_update=True, populate_existing=True)
    assert source is not None and run is not None and company is not None
    if run.state != "collecting" or db.get(CollectionPage, (run_id, offset)) is not None:
        return
    if (
        company.paused
        or not source.enabled
        or source.revision != run.source_revision
        or run.started_at < now() - timedelta(hours=24)
    ):
        run.state = "cancelled" if company.paused or not source.enabled else "expired"
        run.finished_at = now()
        return
    if run.next_offset != offset:
        raise ValueError("Unexpected inventory continuation.")
    issues = set(run.issues) | set(page.issues)
    if source.adapter == "generic_http":
        frontier = list(run.frontier)
        seen_urls = set(frontier)
        for url in page.next_urls:
            if url in seen_urls:
                continue
            if len(frontier) >= 200:
                issues.add("generic_page_limit")
                break
            frontier.append(url)
            seen_urls.add(url)
        run.frontier = frontier
        page = page.model_copy(
            update={"next_offset": offset + 1 if offset + 1 < len(frontier) else None}
        )
    for posting in page.postings:
        external_key = key(posting.external_id)
        association = db.scalar(
            select(JobSource).where(
                JobSource.source_id == source.id,
                JobSource.external_key == external_key,
            )
        )
        if association and db.get(Observation, (run_id, association.id)):
            # Offset pagination shifted or repeated a prior page: never infer omissions.
            issues.add("unstable_pagination")
            if source.adapter == "generic_http":
                # Repeated cards/details must not create contradictory revisions in one epoch.
                continue
        job = (
            db.get(Job, association.job_id)
            if association
            else db.scalar(
                select(Job).where(
                    Job.company_id == source.company_id,
                    Job.canonical_key == key(posting.url),
                )
            )
        )
        created = job is None
        if job is None:
            job = Job(
                company_id=source.company_id,
                canonical_key=key(posting.url),
                baseline=source.baseline_at is None,
            )
            db.add(job)
            db.flush()
        old = db.scalar(
            select(JobRevision).where(
                JobRevision.job_id == job.id,
                JobRevision.revision == job.current_revision,
            )
        )
        if old is None or old.content_hash != posting.content_hash():
            if not created:
                job.current_revision += 1
            revision = JobRevision(
                job_id=job.id,
                revision=job.current_revision,
                content_hash=posting.content_hash(),
                posting=posting.model_dump(mode="json"),
                source_id=source.id,
            )
            db.add(revision)
            db.flush()
            assess_intent(db, job, revision)
        job.last_seen_at = now()
        job.availability = "active"
        if association is None:
            association = JobSource(
                job_id=job.id,
                source_id=source.id,
                external_key=external_key,
                external_id=posting.external_id,
            )
            db.add(association)
            db.flush()
        association.last_seen_at = now()
        association.omissions = 0
        association.available = True
        if db.get(Observation, (run_id, association.id)) is None:
            db.add(Observation(run_id=run_id, association_id=association.id))
    db.add(CollectionPage(run_id=run_id, offset=offset, operation_id=operation_id))
    run.pages += 1
    run.issues = sorted(issues)
    if page.next_offset is not None:
        if page.next_offset <= offset:
            run.issues = sorted(issues | {"invalid_continuation"})
        else:
            run.next_offset = page.next_offset
            page_operation(db, run)
            return
    run.state = "complete" if page.complete and not run.issues else "partial"
    run.finished_at = now()
    source.last_error = None if run.state == "complete" else "incomplete_inventory"
    if (
        source.adapter == "generic_http"
        and db.scalar(
            select(Observation.association_id).where(Observation.run_id == run_id).limit(1)
        )
        is not None
    ):
        # Non-exhaustive sites may never have a fully complete run. End their initial
        # observed baseline so later discoveries do not remain baseline forever.
        source.baseline_at = source.baseline_at or now()
    if run.state != "complete":
        return
    source.last_success_at = now()
    source.baseline_at = source.baseline_at or now()
    if not source.authoritative:
        return
    observed = select(Observation.association_id).where(Observation.run_id == run_id)
    missing = db.scalars(
        select(JobSource).where(
            JobSource.source_id == source.id,
            JobSource.id.not_in(observed),
        )
    )
    affected: set[UUID] = set()
    for association in missing:
        association.omissions += 1
        if association.omissions >= 3:
            association.available = False
        affected.add(association.job_id)
    db.flush()
    for identifier in affected:
        job = db.get(Job, identifier)
        assert job is not None
        update_availability(db, job)
