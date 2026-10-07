"""Persist public input before inference; accept only current, open, attributed output."""

from datetime import timedelta
from uuid import UUID

from app.ai.configuration import capture
from app.ai.extraction import Extraction, context, extract, posting, validate
from app.collection.contracts import InventoryPage
from app.collection.extraction_input import PreparedPage, PublicPage
from app.collection.generic_inventory import name_key
from app.collection.models import CollectionPage, CollectionRun, Company, PageExtraction, Source
from app.config import get_settings
from app.db import get_engine
from app.profile_models import Operation, now
from app.services.operations import OperationError, create_operation
from sqlalchemy import select
from sqlalchemy.orm import Session


def current(
    db: Session, run_id: UUID, offset: int, *, lock: bool = False
) -> tuple[CollectionRun, Source]:
    run = db.get(CollectionRun, run_id)
    source = db.get(Source, run.source_id) if run else None
    company = (
        db.get(Company, source.company_id, with_for_update=lock, populate_existing=lock)
        if source
        else None
    )
    if lock and source is not None and run is not None:
        source = db.get(Source, source.id, with_for_update=True, populate_existing=True)
        run = db.get(CollectionRun, run_id, with_for_update=True, populate_existing=True)
    newer = (
        db.scalar(
            select(CollectionRun.id)
            .where(
                CollectionRun.source_id == run.source_id, CollectionRun.started_at > run.started_at
            )
            .limit(1)
        )
        if run
        else None
    )
    if (
        run is None
        or source is None
        or company is None
        or company.paused
        or not source.enabled
        or source.adapter != "generic_http"
        or source.authoritative
        or source.revision != run.source_revision
        or run.started_at < now() - timedelta(hours=24)
        or run.state not in {"collecting", "failed"}
        or run.next_offset != offset
        or newer
        or db.get(CollectionPage, (run_id, offset)) is not None
    ):
        raise OperationError(
            "extraction_superseded",
            "This page snapshot is no longer current. Start a new company check.",
        )
    return run, source


def stage(db: Session, run_id: UUID, offset: int, prepared: PreparedPage) -> None:
    # Caller holds the operation lease and shared finalization lock.
    _, source = current(db, run_id, offset, lock=True)
    if db.get(PageExtraction, (run_id, offset)):
        return
    assert prepared.extraction is not None
    page = prepared.extraction
    context(
        page.text, page.url, page.links
    )  # No truncation or incomplete input pretending to be complete.
    config_id = capture(db, "job_extraction")
    mode = get_settings().integration_mode
    operation = create_operation(
        db,
        "job_extract",
        f"{run_id}:{offset}",
        {
            "run_id": str(run_id),
            "offset": offset,
            "config_id": config_id,
            "integration_mode": mode,
        },
    )
    db.add(
        PageExtraction(
            run_id=run_id,
            offset=offset,
            operation_id=operation.id,
            config_id=UUID(config_id) if config_id else None,
            integration_mode=mode,
            payload=page.model_dump(mode="json"),
            inventory=prepared.model_dump(mode="json", exclude={"extraction"}),
        )
    )
    source.last_error = "ai_extraction_pending"


def prepare(run_id: UUID, offset: int, operation_id: UUID) -> Extraction:
    with Session(get_engine()) as db:
        current(db, run_id, offset)
        snapshot = db.get(PageExtraction, (run_id, offset))
        if snapshot is None or snapshot.operation_id != operation_id:
            raise OperationError(
                "extraction_snapshot_missing",
                "The saved page is unavailable. Start a new company check.",
            )
        if snapshot.integration_mode != get_settings().integration_mode:
            raise OperationError(
                "extraction_mode_changed",
                "Start a new check in the current integration mode.",
                blocked=True,
            )
        page = PublicPage.model_validate(snapshot.payload)
        config_id = snapshot.config_id
    return extract(page.text, page.url, page.links, config_id, operation_id)


def save(db: Session, run_id: UUID, offset: int, operation_id: UUID, result: Extraction) -> None:
    from app.collection.inventory import apply_page

    run, source = current(db, run_id, offset, lock=True)
    snapshot = db.get(PageExtraction, (run_id, offset))
    if snapshot is None or snapshot.operation_id != operation_id:
        raise OperationError("extraction_snapshot_missing", "The saved page is unavailable.")
    if snapshot.integration_mode != get_settings().integration_mode:
        raise OperationError(
            "extraction_mode_changed",
            "Start a new check in the current integration mode.",
            blocked=True,
        )
    page = PublicPage.model_validate(snapshot.payload)
    spans, urls = context(page.text, page.url, page.links)
    validate(result, spans, urls)
    base = InventoryPage.model_validate(snapshot.inventory)
    issues = set(base.issues) | {"ai_extraction_non_authoritative"}
    accepted = []
    for job in result.jobs:
        if result.coverage not in {"detail", "listing"} or job.status != "open":
            issues.add("extracted_job_not_confirmed_open")
        elif name_key(job.employer.quote) != name_key(source.config["company_name"]):
            issues.add("job_employer_unverified")
        else:
            accepted.append(posting(job, urls))
    if accepted:
        issues.discard("no_verified_generic_jobs")
        issues.discard("no_structured_jobs")
    else:
        issues.add("no_verified_generic_jobs")
    # A deliberate retry may resume a failed epoch while its original snapshot is still current.
    run.state, run.finished_at = "collecting", None
    snapshot.result = result.model_dump(mode="json")
    apply_page(
        db,
        run_id,
        offset,
        base.model_copy(
            update={
                "postings": [*base.postings, *accepted],
                "complete": False,
                "issues": sorted(issues),
            }
        ),
        operation_id,
    )


def supply_missing_configuration(db: Session, operation: Operation) -> None:
    """An explicit retry can fill an unmapped task; never replace a captured model."""
    snapshot = db.get(
        PageExtraction, (UUID(operation.parameters["run_id"]), operation.parameters["offset"])
    )
    if snapshot is not None and snapshot.config_id is None:
        config_id = capture(db, "job_extraction")
        snapshot.config_id = UUID(config_id) if config_id else None
        operation.parameters = {**operation.parameters, "config_id": config_id}


def failure(
    db: Session, run_id: UUID, offset: int, code: str, *, terminal: bool, retry_after: int | None
) -> None:
    from app.collection.runner import record_failure

    try:
        run, _ = current(db, run_id, offset, lock=True)
    except OperationError:
        return  # Never change a newer/superseded source's status.
    run.state, run.finished_at = "collecting", None
    record_failure(db, run_id, code, terminal=terminal, retry_after=retry_after)
