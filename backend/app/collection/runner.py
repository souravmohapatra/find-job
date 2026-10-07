"""Bounded page preparation; database writes happen only after lease validation."""

from datetime import timedelta
from typing import cast
from uuid import UUID

from app.collection.ats import decode_page, request_url
from app.collection.contracts import Adapter, InventoryPage
from app.collection.models import CollectionRun, Company, Observation, Source
from app.db import get_engine
from app.profile_models import now
from app.services.operations import OperationError
from sqlalchemy import select
from sqlalchemy.orm import Session


def prepare_page(run_id: UUID, offset: int) -> InventoryPage:
    with Session(get_engine()) as db:
        run = db.get(CollectionRun, run_id)
        if run is None or run.state != "collecting" or run.next_offset != offset:
            raise OperationError(
                "collection_superseded", "This collection run is no longer current."
            )
        source = db.get(Source, run.source_id)
        assert source is not None
        company = db.get(Company, source.company_id)
        if (
            company is None
            or company.paused
            or not source.enabled
            or source.revision != run.source_revision
            or run.started_at < now() - timedelta(hours=24)
        ):
            raise OperationError(
                "collection_superseded", "This collection run is no longer current."
            )
        if source.cooldown_until and source.cooldown_until > now():
            raise OperationError(
                "source_cooldown",
                "This source is waiting before its next request.",
                retryable=True,
                retry_after=max(1, int((source.cooldown_until - now()).total_seconds())),
            )
        if source.adapter == "generic_http":
            generic_config = (
                run.frontier[offset],
                source.config["company_name"],
                source.config["website"],
            )
        else:
            generic_config = None
        if source.adapter not in {"greenhouse", "lever", "ashby", "generic_http"}:
            raise OperationError(
                "adapter_unavailable", "This source adapter is not configured.", blocked=True
            )
        source_id, source_revision = source.id, source.revision
        adapter = cast(Adapter, source.adapter)
        url = (
            generic_config[0]
            if generic_config
            else request_url(
                adapter,
                source.config["board"],
                region=source.config.get("region", "global"),
                offset=offset,
            )
        )
    from app.collection import cache, generic_inventory, transport
    from app.collection.extraction_input import PreparedPage

    remote = generic_inventory.fetch_document if generic_config else transport.fetch_document
    document, snapshot = cache.fetch(source_id, source_revision, url, remote)
    page = (
        generic_inventory.collect(*generic_config, document=document)
        if generic_config
        else decode_page(adapter, transport.parse_json(document), offset=offset)
    )
    if isinstance(page, PreparedPage):
        return page.model_copy(update={"snapshot": snapshot})
    return PreparedPage(**page.model_dump(), snapshot=snapshot)


def record_failure(
    db: Session, run_id: UUID, code: str, *, terminal: bool, retry_after: int | None
) -> None:
    initial = db.get(CollectionRun, run_id)
    if initial is None:
        return
    source = db.get(Source, initial.source_id, with_for_update=True)
    run = db.get(CollectionRun, run_id, with_for_update=True, populate_existing=True)
    if source is None or run is None or run.state != "collecting":
        return
    if source.revision != run.source_revision:
        run.state = "cancelled"
        run.finished_at = now()
        run.issues = sorted(set(run.issues) | {"source_changed"})
        return
    source.last_error = code
    if retry_after:
        source.cooldown_until = now() + timedelta(seconds=retry_after)
    if terminal:
        if (
            source.adapter == "generic_http"
            and db.scalar(
                select(Observation.association_id).where(Observation.run_id == run_id).limit(1)
            )
            is not None
        ):
            source.baseline_at = source.baseline_at or now()
        run.state = "failed"
        run.finished_at = now()
        run.issues = sorted(set(run.issues) | {code})
