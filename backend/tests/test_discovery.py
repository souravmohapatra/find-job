from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from app.collection import discovery
from app.collection.discovery import begin, schedule, target
from app.collection.models import Company, DiscoveryRun, Source
from app.db import get_engine
from app.fetcher.contracts import FetchRequest, FetchResult
from app.profile_models import Operation, now
from app.services.operations import OperationError, create_operation, process_operation
from sqlalchemy import func, select
from sqlalchemy.orm import Session


def watch(website: str | None = "https://example.com") -> tuple[UUID, UUID]:
    with Session(get_engine()) as db, db.begin():
        company = Company(label="Example", website=website)
        db.add(company)
        db.flush()
        operation = create_operation(
            db, "company_discover", str(uuid4()), {"company_id": str(company.id)}
        )
        return company.id, operation.id


def next_step() -> UUID | None:
    with Session(get_engine()) as db:
        return db.scalar(
            select(Operation.id)
            .where(Operation.kind == "discovery_step", Operation.state == "queued")
            .order_by(Operation.created_at)
            .limit(1)
        )


def drain() -> None:
    for _ in range(25):
        identifier = next_step()
        if identifier is None:
            return
        process_operation(identifier)
    raise AssertionError("Discovery exceeded its bounded step count")


def document(request: FetchRequest, html: str) -> FetchResult:
    return FetchResult(url=request.url, status=200, content_type="text/html", body=html)


def test_official_link_empty_board_restart_replay_and_scheduled_rediscovery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def fetch(request: FetchRequest) -> FetchResult:
        calls.append(request.url)
        if request.url == "https://example.com/":
            return document(request, '<a href="/careers">Careers</a>')
        return document(request, '<a href="https://jobs.lever.co/example">Open roles</a>')

    monkeypatch.setattr(discovery, "fetch_document", fetch)
    monkeypatch.setattr(discovery, "fetch_json", lambda url: [])
    company_id, root = watch()
    process_operation(root)
    first = next_step()
    assert first
    process_operation(first)
    with Session(get_engine()) as db, db.begin():
        run = db.scalar(select(DiscoveryRun))
        assert run.cursor == 1 and len(run.frontier) == 2
        company = db.get(Company, company_id, with_for_update=True)
        joined = begin(db, company)
        assert joined.id == next_step()
    process_operation(first)  # Replay must neither fetch nor advance again.
    drain()
    assert calls == ["https://example.com/", "https://example.com/careers"]
    with Session(get_engine()) as db, db.begin():
        run = db.scalar(select(DiscoveryRun))
        source = db.scalar(select(Source))
        company = db.get(Company, company_id)
        assert run.state == "complete" and run.cursor == 3
        assert source.adapter == "lever" and source.config["board"] == "example"
        assert source.evidence["linked_from"] == "https://example.com/careers"
        assert source.evidence["network_verified"] is True
        assert company.resolution == "sources_found"
        assert company.discovery_due_at > now() + timedelta(days=6)
        source.enabled = False
        company.discovery_due_at = now() - timedelta(seconds=1)
        assert schedule(db) == 1
    drain()
    with Session(get_engine()) as db:
        assert db.scalar(select(func.count()).select_from(Source)) == 1
        assert db.scalar(select(Source)).enabled is False


@pytest.mark.parametrize(
    ("url", "adapter", "board", "region"),
    [
        ("https://job-boards.greenhouse.io/studio/jobs/123", "greenhouse", "studio", "global"),
        (
            "https://boards.greenhouse.io/embed/job_board?for=studio",
            "greenhouse",
            "studio",
            "global",
        ),
        ("https://jobs.eu.lever.co/studio/123", "lever", "studio", "eu"),
        ("https://jobs.ashbyhq.com/studio/123", "ashby", "studio", "global"),
        ("https://jobs.lever.co.evil.example/studio", None, None, "global"),
    ],
)
def test_ats_identity_uses_exact_hosts(
    url: str, adapter: str | None, board: str | None, region: str
) -> None:
    found = target(url)
    assert (found.adapter, found.board, found.region) == (adapter, board, region)


def test_no_website_remains_visible_without_synthetic_jobs() -> None:
    company_id, root = watch(None)
    process_operation(root)
    with Session(get_engine()) as db:
        company = db.get(Company, company_id)
        assert company.resolution == "needs_website"
        assert company.evidence["discovery_issue"] == "search_discovery_pending"
        assert company.discovery_due_at > now()
        assert db.scalar(select(func.count()).select_from(Source)) == 0


def test_page_failure_preserves_other_paths_and_invalid_ats_is_not_verified(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fetch(request: FetchRequest) -> FetchResult:
        if request.url.endswith("/careers"):
            raise OperationError("robots_denied", "This page disallows fetching.", blocked=True)
        return document(
            request,
            '<a href="/careers">Careers</a><a href="https://jobs.ashbyhq.com/example">Jobs</a>',
        )

    monkeypatch.setattr(discovery, "fetch_document", fetch)
    monkeypatch.setattr(discovery, "fetch_json", lambda url: {"error": "no board"})
    _, root = watch()
    process_operation(root)
    drain()
    with Session(get_engine()) as db:
        run = db.scalar(select(DiscoveryRun))
        assert run.state == "partial" and run.cursor == 3
        assert "robots_denied" in run.issues and "ats_response_unverified" in run.issues
        assert db.scalar(select(func.count()).select_from(Source)) == 0


def test_changed_company_and_lost_lease_discard_results(monkeypatch: pytest.MonkeyPatch) -> None:
    company_id, root = watch("https://jobs.lever.co/example")
    process_operation(root)
    step = next_step()
    assert step

    def stale(url: str) -> list[object]:
        with Session(get_engine()) as db, db.begin():
            company = db.get(Company, company_id)
            company.revision += 1
        return []

    monkeypatch.setattr(discovery, "fetch_json", stale)
    process_operation(step)
    with Session(get_engine()) as db, db.begin():
        assert db.scalar(select(DiscoveryRun)).state == "cancelled"
        assert db.scalar(select(Source)) is None
        company = db.get(Company, company_id, with_for_update=True)
        step = begin(db, company).id

    def lost(url: str) -> list[object]:
        with Session(get_engine()) as db, db.begin():
            db.get(Operation, step).lease_token = uuid4()
        return []

    monkeypatch.setattr(discovery, "fetch_json", lost)
    process_operation(step)
    with Session(get_engine()) as db:
        active = db.scalar(select(DiscoveryRun).where(DiscoveryRun.state == "running"))
        assert active.cursor == 0 and db.scalar(select(Source)) is None


def test_unknown_redirect_caps_and_generic_candidates_are_not_verified_jobs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fetch(request: FetchRequest) -> FetchResult:
        if request.url.endswith("/careers"):
            return FetchResult(
                url="https://unrelated.example/careers",
                status=200,
                content_type="text/html",
                body='<a href="https://jobs.lever.co/wrong">Jobs</a>',
            )
        return document(
            request,
            '<script type="application/ld+json">'
            '{"@type":"JobPosting","title":"Engineer","description":"Build things"}'
            '</script><a href="/careers">Careers</a>'
            + "".join(f'<a href="/jobs/{n}">Job</a>' for n in range(25)),
        )

    monkeypatch.setattr(discovery, "fetch_document", fetch)
    _, root = watch()
    process_operation(root)
    drain()
    with Session(get_engine()) as db:
        run = db.scalar(select(DiscoveryRun))
        assert run.cursor == 20 and len(run.frontier) == 20
        assert "discovery_page_limit" in run.issues and "unverified_redirect" in run.issues
        assert run.candidates and "generic_collection_pending" in run.issues
        assert db.scalar(select(Source)) is None


def test_interrupted_final_step_is_reconciled_and_expired_epoch_is_replaced() -> None:
    company_id, root = watch()
    process_operation(root)
    with Session(get_engine()) as db, db.begin():
        company = db.get(Company, company_id, with_for_update=True)
        run = db.scalar(select(DiscoveryRun))
        operation = db.get(Operation, next_step())
        operation.state = "failed"
        db.flush()
        assert begin(db, company) is None
        assert run.state == "partial" and "discovery_step_interrupted" in run.issues
        assert begin(db, company) is not None
    with Session(get_engine()) as db, db.begin():
        active = db.scalar(select(DiscoveryRun).where(DiscoveryRun.state == "running"))
        active.started_at = now() - timedelta(hours=25)
        previous_id = active.id
        company = db.get(Company, company_id, with_for_update=True)
        assert begin(db, company) is not None
        assert db.get(DiscoveryRun, previous_id).state == "expired"


def test_discovery_history_is_authenticated_and_does_not_expose_fetch_frontier(client, monkeypatch):
    from test_inventory_api import auth

    monkeypatch.setattr(
        discovery, "fetch_document", lambda request: document(request, "No careers page")
    )
    company_id, root = watch()
    endpoint = f"/api/v1/companies/{company_id}/discovery"
    assert client.get(endpoint).status_code == 401
    auth(client)
    process_operation(root)
    drain()
    history = client.get(endpoint)
    assert history.status_code == 200
    assert history.json()[0]["state"] == "complete"
    assert history.json()[0]["cursor"] == 1
    assert "frontier" not in history.json()[0]
    assert client.get(endpoint + "?offset=20").json() == []
    assert client.get(f"/api/v1/companies/{uuid4()}/discovery").status_code == 404


def test_tick_releases_source_locks_before_discovery_company_locks(monkeypatch):
    from app.tasks import worker
    from sqlalchemy import text
    from test_inventory import source

    with Session(get_engine()) as db, db.begin():
        row = source(db)
        source_id, company_id = row.id, row.company_id
    original = discovery.schedule
    checked = []

    def with_concurrent_collector(db):
        # A separate collector finalizes in company -> source lock order.
        # It must not be blocked by the scheduler waiting for company locks.
        with Session(get_engine()) as collector, collector.begin():
            collector.execute(text("SET LOCAL lock_timeout = '500ms'"))
            collector.get(Company, company_id, with_for_update=True)
            collector.get(Source, source_id, with_for_update=True)
            checked.append(True)
        return original(db)

    monkeypatch.setattr(discovery, "schedule", with_concurrent_collector)
    monkeypatch.setattr(worker, "dispatch", lambda: 0)
    worker.tick(0)
    assert checked == [True]
