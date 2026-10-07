"""Bounded page preparation; database writes happen only after lease validation."""

from datetime import timedelta
from typing import Any, cast
from uuid import UUID

from app.collection.ats import decode_page, request_url
from app.collection.contracts import Adapter, InventoryPage
from app.collection.models import CollectionRun, Company, Source
from app.db import get_engine
from app.profile_models import now
from app.services.operations import OperationError
from sqlalchemy.orm import Session


def fetch_json(url: str) -> Any:
    from app.collection.transport import fetch_json as remote_fetch

    return remote_fetch(url)


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
        if source.adapter not in {"greenhouse", "lever", "ashby"}:
            raise OperationError(
                "adapter_unavailable", "This source adapter is not configured.", blocked=True
            )
        adapter = cast(Adapter, source.adapter)
        url = request_url(
            adapter,
            source.config["board"],
            region=source.config.get("region", "global"),
            offset=offset,
        )
    return decode_page(adapter, fetch_json(url), offset=offset)


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
        run.state = "failed"
        run.finished_at = now()
        run.issues = sorted(set(run.issues) | {code})
