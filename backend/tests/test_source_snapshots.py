import json
from datetime import timedelta
from uuid import uuid4

import pytest
from app.collection import cache, generic_inventory, transport
from app.collection.contracts import InventoryPage
from app.collection.inventory import begin_run
from app.collection.models import CollectionRun, Job, JobRevision, JobSource, Source, SourceSnapshot
from app.db import get_engine
from app.fetcher.contracts import FetchResult
from app.profile_models import Operation, now
from app.services.operations import OperationError, process_operation
from app.services.retention import expire_source_snapshots
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_inventory import collect, posting, source


def response(url, status=200, body=None, **extra):
    return FetchResult(
        url=url,
        status=status,
        body=body
        if body is not None
        else json.dumps(
            [
                {
                    "id": "a",
                    "text": "Strategy role",
                    "descriptionPlain": "Lead planning.",
                    "hostedUrl": "https://jobs.lever.co/synthetic/a",
                    "applyUrl": "https://jobs.lever.co/synthetic/a/apply",
                }
            ]
        ),
        content_type="application/json",
        etag='"v1"',
        **extra,
    )


def start(source_id=None):
    with Session(get_engine()) as db, db.begin():
        row = db.get(Source, source_id) if source_id else source(db)
        operation = begin_run(db, row)
        return row.id, operation.id


def test_304_replays_inventory_without_duplicate_revisions_or_false_omissions(monkeypatch):
    requests = []

    def remote(request):
        requests.append(request)
        return response(
            request.url, 200 if len(requests) == 1 else 304, body=None if len(requests) == 1 else ""
        )

    monkeypatch.setattr(transport, "fetch_document", remote)
    source_id, operation_id = start()
    process_operation(operation_id)
    for _ in range(3):
        _, operation_id = start(source_id)
        process_operation(operation_id)
    assert requests[0].etag is None and all(request.etag == '"v1"' for request in requests[1:])
    with Session(get_engine()) as db:
        assert db.scalar(select(func.count()).select_from(JobRevision)) == 1
        assert db.scalar(select(Job)).availability == "active"
        assert db.scalar(select(JobSource)).omissions == 0
        assert db.scalar(select(func.count()).select_from(SourceSnapshot)) == 1
        assert all(run.state == "complete" for run in db.scalars(select(CollectionRun)))


@pytest.mark.parametrize("invalidation", ["revision", "expiry", "corruption", "missing"])
def test_unusable_snapshot_does_not_send_validators_or_accept_bare_304(monkeypatch, invalidation):
    monkeypatch.setattr(transport, "fetch_document", lambda request: response(request.url))
    source_id, operation_id = start()
    process_operation(operation_id)
    with Session(get_engine()) as db, db.begin():
        row = db.scalar(select(SourceSnapshot))
        if invalidation == "revision":
            db.get(Source, source_id).revision += 1
        elif invalidation == "expiry":
            row.fetched_at = now() - timedelta(days=8)
        elif invalidation == "corruption":
            row.body_hash = "0" * 64
        else:
            db.delete(row)
    seen = []

    def unchanged(request):
        seen.append(request)
        return response(request.url, 304, "")

    monkeypatch.setattr(transport, "fetch_document", unchanged)
    _, operation_id = start(source_id)
    process_operation(operation_id)
    assert seen[0].etag is None and seen[0].modified_since is None
    with Session(get_engine()) as db:
        assert db.get(Operation, operation_id).error_code == "source_snapshot_missing"
        assert db.scalar(select(Job)).availability == "active"
        assert db.scalar(select(JobSource)).omissions == 0


def test_lost_lease_does_not_save_snapshot_or_inventory(monkeypatch):
    source_id, operation_id = start()

    def remote(request):
        with Session(get_engine()) as db, db.begin():
            db.get(Operation, operation_id).lease_token = uuid4()
        return response(request.url)

    monkeypatch.setattr(transport, "fetch_document", remote)
    process_operation(operation_id)
    with Session(get_engine()) as db:
        assert db.scalar(select(SourceSnapshot)) is None
        assert db.scalar(select(Job)) is None


def test_generic_304_is_reparsed_and_stays_non_authoritative(monkeypatch):
    body = """<script type="application/ld+json">{"@type":"JobPosting","title":"Strategy role",
    "description":"Lead planning.","url":"https://careers.example.com/a",
    "hiringOrganization":{"name":"Synthetic company"}}</script>"""
    with Session(get_engine()) as db, db.begin():
        row = source(db)
        row.adapter, row.authoritative = "generic_http", False
        row.url = "https://careers.example.com/jobs"
        row.config = {"company_name": "Synthetic company", "website": "https://careers.example.com"}
        source_id = row.id
    seen = []

    def remote(request):
        seen.append(request)
        return FetchResult(
            url=request.url,
            status=200 if len(seen) == 1 else 304,
            body=body if len(seen) == 1 else "",
            content_type="text/html",
            etag='"g1"',
        )

    monkeypatch.setattr(generic_inventory, "fetch_document", remote)
    for _ in range(2):
        _, operation_id = start(source_id)
        process_operation(operation_id)
    assert seen[1].etag == '"g1"'
    with Session(get_engine()) as db:
        assert db.scalar(select(Job)).availability == "active"
        assert db.scalar(select(func.count()).select_from(JobRevision)) == 1
        assert db.scalar(select(SourceSnapshot)) is not None
        assert not db.get(Source, source_id).authoritative


def test_changed_full_response_replaces_snapshot_and_no_store_removes_it(monkeypatch):
    monkeypatch.setattr(transport, "fetch_document", lambda request: response(request.url))
    source_id, operation_id = start()
    process_operation(operation_id)
    monkeypatch.setattr(
        transport,
        "fetch_document",
        lambda request: response(request.url, body="[]", cacheable=False),
    )
    _, operation_id = start(source_id)
    process_operation(operation_id)
    with Session(get_engine()) as db:
        assert db.scalar(select(SourceSnapshot)) is None
        assert (
            db.scalar(select(JobSource)).omissions == 1
        )  # Normal complete-empty policy still applies.
        assert db.scalar(select(Job)).availability == "active"


def test_modified_date_validator_and_mismatched_etag(monkeypatch):
    source_id, _ = start()
    url = "https://example.com/jobs"
    document = response(url).model_copy(
        update={"etag": None, "modified": "Wed, 07 Oct 2026 19:00:00 GMT"}
    )
    with Session(get_engine()) as db, db.begin():
        cache.save(
            db,
            db.get(Source, source_id),
            cache.SnapshotUpdate(url=url, document=document, fetched_at=now()),
        )
    seen = []

    def remote(request):
        seen.append(request)
        return response(url, 304, "").model_copy(update={"etag": None})

    result, _ = cache.fetch(source_id, 1, url, remote)
    assert result.body == document.body and seen[0].modified_since == document.modified
    with Session(get_engine()) as db, db.begin():
        cache.save(
            db,
            db.get(Source, source_id),
            cache.SnapshotUpdate(url=url, document=response(url), fetched_at=now()),
        )
    with pytest.raises(OperationError, match="conflicting page validators"):
        cache.fetch(
            source_id,
            1,
            url,
            lambda request: response(url, 304, "").model_copy(update={"etag": '"other"'}),
        )


def test_expiry_and_page_cap_keep_normalized_jobs(monkeypatch):
    with Session(get_engine()) as db, db.begin():
        row = source(db)
        collect(db, row, InventoryPage(postings=[posting()], complete=True))
        for i in range(201):
            url = f"https://example.com/jobs/{i}"
            cache.save(
                db,
                row,
                cache.SnapshotUpdate(
                    url=url, document=response(url), fetched_at=now() - timedelta(days=8)
                ),
            )
            db.flush()
        assert db.scalar(select(func.count()).select_from(SourceSnapshot)) == 200
    assert expire_source_snapshots() == 100
    assert expire_source_snapshots() == 100
    with Session(get_engine()) as db:
        assert db.scalar(select(Job)).availability == "active"


@pytest.mark.parametrize("changed", ["redirect", "url", "source"])
def test_conditional_reuse_never_crosses_redirect_url_or_source(changed):
    source_id, _ = start()
    url = "https://example.com/jobs?page=1"
    with Session(get_engine()) as db, db.begin():
        cache.save(
            db,
            db.get(Source, source_id),
            cache.SnapshotUpdate(url=url, document=response(url), fetched_at=now()),
        )
        other_id = source(db).id
    target_url = url.replace("page=1", "page=2") if changed == "url" else url
    target_id = other_id if changed == "source" else source_id
    with pytest.raises(OperationError, match="without a usable saved page"):
        cache.fetch(
            target_id,
            1,
            target_url,
            lambda request: response(target_url, 304, "", redirected=changed == "redirect"),
        )


def test_new_source_revision_during_fetch_discards_snapshot(monkeypatch):
    source_id, operation_id = start()

    def remote(request):
        with Session(get_engine()) as db, db.begin():
            db.get(Source, source_id).revision += 1
        return response(request.url)

    monkeypatch.setattr(transport, "fetch_document", remote)
    process_operation(operation_id)
    with Session(get_engine()) as db:
        assert db.scalar(select(SourceSnapshot)) is None
        assert db.scalar(select(Job)) is None


def test_generic_304_rechecks_expiry_in_current_parser(monkeypatch):
    from datetime import UTC, datetime

    from app.collection.generic import parse_page

    body = """<script type="application/ld+json">{"@type":"JobPosting","title":"Strategy role",
    "description":"Lead planning.","url":"https://careers.example.com/a",
    "validThrough":"2026-10-08T12:00:00Z",
    "hiringOrganization":{"name":"Synthetic company"}}</script>"""
    instant = datetime(2026, 10, 7, tzinfo=UTC)
    monkeypatch.setattr(
        generic_inventory, "parse_page", lambda body, url: parse_page(body, url, now=instant)
    )
    with Session(get_engine()) as db, db.begin():
        row = source(db)
        row.adapter, row.authoritative = "generic_http", False
        row.url = "https://careers.example.com/jobs"
        row.config = {"company_name": "Synthetic company", "website": "https://careers.example.com"}
        source_id = row.id
    calls = []

    def remote(request):
        calls.append(request)
        return FetchResult(
            url=request.url,
            status=200 if len(calls) == 1 else 304,
            body=body if len(calls) == 1 else "",
            content_type="text/html",
            etag='"v1"',
        )

    monkeypatch.setattr(generic_inventory, "fetch_document", remote)
    _, operation_id = start(source_id)
    process_operation(operation_id)
    instant = datetime(2026, 10, 9, tzinfo=UTC)
    _, operation_id = start(source_id)
    process_operation(operation_id)
    with Session(get_engine()) as db:
        latest = db.scalar(select(CollectionRun).order_by(CollectionRun.started_at.desc()))
        assert latest.state == "partial" and "expired_job_evidence" in latest.issues
        assert (
            db.scalar(select(Job)).availability == "active"
        )  # Non-authoritative absence never closes.
    assert calls[1].etag == '"v1"'


def test_updated_representation_replaces_validator_and_replays_latest_body(monkeypatch):
    seen = []

    def remote(request):
        seen.append(request.etag)
        if len(seen) == 1:
            return response(request.url)
        if len(seen) == 2:
            document = response(request.url)
            return document.model_copy(
                update={
                    "etag": '"v2"',
                    "body": document.body.replace("Lead planning.", "Lead new planning."),
                }
            )
        return response(request.url, 304, "").model_copy(update={"etag": '"v2"'})

    monkeypatch.setattr(transport, "fetch_document", remote)
    source_id, operation_id = start()
    process_operation(operation_id)
    for _ in range(2):
        _, operation_id = start(source_id)
        process_operation(operation_id)
    assert seen == [None, '"v1"', '"v2"']
    with Session(get_engine()) as db:
        assert db.scalar(select(Job)).current_revision == 2
        assert db.scalar(select(func.count()).select_from(JobRevision)) == 2
        assert db.scalar(select(SourceSnapshot)).document["etag"] == '"v2"'
