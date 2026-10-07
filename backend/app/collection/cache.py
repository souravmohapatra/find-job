"""Revalidate bounded public snapshots; no stale-on-error or empty-304 inventories."""

import hashlib
import re
from collections.abc import Callable
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from uuid import UUID

from app.collection.models import Source, SourceSnapshot
from app.db import get_engine
from app.fetcher.contracts import FetchRequest, FetchResult
from app.profile_models import now
from app.services.operations import OperationError
from pydantic import BaseModel, ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session


class SnapshotUpdate(BaseModel):
    url: str
    document: FetchResult | None
    fetched_at: datetime


def key(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def validators(document: FetchResult) -> tuple[str | None, str | None]:
    etag, modified = document.etag, document.modified
    if not etag or len(etag) > 1000 or not re.fullmatch(r'(?:W/)?"[\x21\x23-\x7e]*"', etag):
        etag = None
    try:
        if (
            not modified
            or len(modified) > 1000
            or not all(32 <= ord(character) < 127 for character in modified)
            or parsedate_to_datetime(modified).tzinfo is None
        ):
            modified = None
    except (ValueError, TypeError, OverflowError):
        modified = None
    return etag, modified


def fetch(
    source_id: UUID,
    revision: int,
    url: str,
    remote: Callable[[FetchRequest], FetchResult],
) -> tuple[FetchResult, SnapshotUpdate]:
    cached = None
    with Session(get_engine()) as db:
        row = db.get(SourceSnapshot, (source_id, key(url)))
        if row and row.source_revision == revision and row.fetched_at > now() - timedelta(days=7):
            try:
                candidate = FetchResult.model_validate(row.document)
                if (
                    candidate.status == 200
                    and candidate.url == url
                    and candidate.cacheable
                    and not candidate.redirected
                    and row.body_hash == key(candidate.body)
                ):
                    cached = candidate
            except ValidationError:
                pass  # An unusable cache entry requires a full request.
    etag, modified = validators(cached) if cached else (None, None)
    document = remote(FetchRequest(url=url, etag=etag, modified_since=modified))
    if document.status == 304:
        if cached is None or not (etag or modified) or document.url != url or document.redirected:
            raise OperationError(
                "source_snapshot_missing",
                "The source returned unchanged content without a usable saved page.",
            )
        response_etag, response_modified = validators(document)
        if response_etag and etag and response_etag.removeprefix("W/") != etag.removeprefix("W/"):
            raise OperationError(
                "source_validator_conflict", "The source returned conflicting page validators."
            )
        document = cached.model_copy(
            update={
                "etag": response_etag or etag,
                "modified": response_modified or modified,
                "cacheable": document.cacheable,
            }
        )
    etag, modified = validators(document)
    storable = (
        document.status == 200
        and document.url == url
        and not document.redirected
        and document.cacheable
        and (etag or modified)
    )
    # The caller persists this only after successful parsing and current-lease/source checks.
    update = SnapshotUpdate(
        url=url,
        document=document.model_copy(update={"etag": etag, "modified": modified})
        if storable
        else None,
        fetched_at=now(),
    )
    return document, update


def save(db: Session, source: Source, update: SnapshotUpdate | None) -> None:
    """Caller holds company/source locks after validating the worker lease and run."""
    if update is None:
        return
    identity = (source.id, key(update.url))
    row = db.get(SourceSnapshot, identity)
    if row and row.fetched_at > update.fetched_at:
        return
    if update.document is None:
        if row:
            db.delete(row)
        return
    if row is None:
        count = (
            db.scalar(
                select(func.count())
                .select_from(SourceSnapshot)
                .where(SourceSnapshot.source_id == source.id)
            )
            or 0
        )
        if count >= 200:
            oldest = db.scalar(
                select(SourceSnapshot)
                .where(SourceSnapshot.source_id == source.id)
                .order_by(SourceSnapshot.fetched_at)
                .limit(1)
            )
            if oldest:
                db.delete(oldest)
        row = SourceSnapshot(source_id=source.id, url_hash=identity[1])
        db.add(row)
    row.source_revision = source.revision
    row.document = update.document.model_dump(mode="json")
    row.body_hash = key(update.document.body)
    row.fetched_at = update.fetched_at
