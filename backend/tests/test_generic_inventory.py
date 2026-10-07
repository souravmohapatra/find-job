import json
from uuid import UUID

import pytest
from app.collection import discovery, generic_inventory
from app.collection.generic import parse_page
from app.collection.inventory import begin_run
from app.collection.models import Company, DiscoveryRun, Job, JobRevision, JobSource, Source
from app.db import get_engine
from app.fetcher.contracts import FetchResult
from app.profile_models import Operation
from app.services.operations import process_operation
from sqlalchemy import select
from sqlalchemy.orm import Session


def html(*rows):
    return '<script type="application/ld+json">' + json.dumps(list(rows)) + "</script>"


def posting(**changes):
    return {
        "@type": "JobPosting",
        "title": "Strategy manager",
        "description": "Plan new markets",
        "url": "https://example.com/jobs/one",
        "hiringOrganization": {"name": "Example"},
        **changes,
    }


def test_employer_identity_and_expiry_are_required_before_inventory():
    page = parse_page(
        html(
            posting(),
            posting(url="/jobs/other", hiringOrganization={"name": "Other"}),
            posting(url="/jobs/expired", validThrough="2020-01-01"),
        ),
        "https://example.com/jobs",
    )
    result = generic_inventory.inventory(page, "Example", "https://example.com")
    assert len(result.postings) == 1
    assert not result.complete
    assert result.issues == ["expired_job_evidence", "job_employer_unverified"]
    page = parse_page(
        html(
            posting(
                hiringOrganization={
                    "name": "Example Legal Entity",
                    "url": "https://example.com/about",
                }
            )
        ),
        "https://example.com/jobs",
    )
    assert len(generic_inventory.inventory(page, "Example", "https://example.com").postings) == 1


def test_generic_discovery_source_worker_revision_and_omission_safety(monkeypatch):
    content = [html(posting())]

    def fetch(request):
        return FetchResult(url=request.url, status=200, content_type="text/html", body=content[0])

    monkeypatch.setattr(discovery, "fetch_document", fetch)
    monkeypatch.setattr(generic_inventory, "fetch_document", fetch)
    with Session(get_engine()) as db, db.begin():
        company = Company(label="Example", website="https://example.com/jobs")
        db.add(company)
        db.flush()
        operation = discovery.begin(db, company)
        identifier = operation.id
    process_operation(identifier)
    with Session(get_engine()) as db, db.begin():
        source = db.scalar(select(Source))
        assert source.adapter == "generic_http" and source.authoritative is False
        assert db.scalar(select(DiscoveryRun)).candidates[0]["status"] == "source_collection_queued"
        source_id = source.id
        operation = begin_run(db, source)
        identifier = operation.id
    process_operation(identifier)
    process_operation(identifier)
    with Session(get_engine()) as db:
        job = db.scalar(select(Job))
        assert job.current_revision == 1
        job_id = job.id
        assert db.scalar(select(Operation).where(Operation.id == identifier)).state == "succeeded"
    content[0] = html(posting(description="Plan global markets"))
    with Session(get_engine()) as db, db.begin():
        operation = begin_run(db, db.get(Source, source_id, with_for_update=True))
        identifier = operation.id
    process_operation(identifier)
    with Session(get_engine()) as db:
        assert db.get(Job, job_id).current_revision == 2
        assert (
            db.scalar(select(JobRevision).where(JobRevision.revision == 2)).posting["description"]
            == "Plan global markets"
        )
    # Repeated empty/malformed pages never close the observed role.
    content[0] = "<h1>Jobs</h1><p>Try again later</p>"
    for _ in range(3):
        with Session(get_engine()) as db, db.begin():
            identifier = begin_run(db, db.get(Source, source_id, with_for_update=True)).id
        process_operation(identifier)
    with Session(get_engine()) as db:
        assert db.get(Job, job_id).availability == "active"
        assert db.scalar(select(JobSource)).omissions == 0
        assert db.get(Source, source_id).last_error == "incomplete_inventory"


@pytest.mark.parametrize(
    "url,status,media,code",
    [
        ("https://other.example/jobs", 200, "text/html", "generic_redirect_unverified"),
        ("https://example.com/jobs", 404, "text/html", "generic_http_error"),
        ("https://example.com/jobs", 200, "application/json", "generic_content_type"),
    ],
)
def test_unverified_response_never_becomes_inventory(monkeypatch, url, status, media, code):
    from app.services.operations import OperationError

    monkeypatch.setattr(
        generic_inventory,
        "fetch_document",
        lambda request: FetchResult(
            url=url, status=status, content_type=media, body=html(posting())
        ),
    )
    with pytest.raises(OperationError) as error:
        generic_inventory.collect("https://example.com/jobs", "Example", "https://example.com")
    assert error.value.code == code


def test_generic_frontier_survives_restart_deduplicates_links_and_finishes_baseline(monkeypatch):
    from app.collection.inventory import key
    from app.collection.models import CollectionRun
    from app.profile_models import now

    calls = []

    def fetch(request):
        calls.append(request.url)
        if request.url == "https://example.com/jobs":
            body = (
                html(posting())
                + '<a href="/jobs/two" rel="next">Next</a><a href="/jobs/two">Duplicate</a>'
            )
        else:
            body = '<h1>Temporarily unavailable</h1><a href="/jobs">Back</a>'
        return FetchResult(url=request.url, status=200, content_type="text/html", body=body)

    monkeypatch.setattr(generic_inventory, "fetch_document", fetch)
    with Session(get_engine()) as db, db.begin():
        company = Company(label="Example", website="https://example.com")
        db.add(company)
        db.flush()
        source = Source(
            company_id=company.id,
            identity=key("generic"),
            adapter="generic_http",
            url="https://example.com/jobs",
            authoritative=False,
            config={"company_name": "Example", "website": "https://example.com"},
        )
        db.add(source)
        db.flush()
        source_id = source.id
        first = begin_run(db, source)
        first_id = first.id
        run_id = UUID(first.parameters["run_id"])
    process_operation(first_id)
    with Session(get_engine()) as db, db.begin():
        epoch = db.get(CollectionRun, run_id)
        assert epoch.frontier == ["https://example.com/jobs", "https://example.com/jobs/two"]
        assert epoch.next_offset == 1 and epoch.pages == 1
        second = begin_run(db, db.get(Source, source_id, with_for_update=True))
        second_id = second.id
    process_operation(first_id)
    process_operation(second_id)
    with Session(get_engine()) as db, db.begin():
        epoch = db.get(CollectionRun, run_id)
        source = db.get(Source, source_id)
        assert epoch.state == "partial" and epoch.pages == 2
        assert source.baseline_at and source.baseline_at <= now()
        assert db.scalar(select(Job)).baseline is True
        source.next_due_at = now()
    assert calls == ["https://example.com/jobs", "https://example.com/jobs/two"]
    monkeypatch.setattr(
        generic_inventory,
        "fetch_document",
        lambda request: FetchResult(
            url=request.url,
            status=200,
            content_type="text/html",
            body=html(posting(url="https://example.com/jobs/new", title="Legal adviser")),
        ),
    )
    with Session(get_engine()) as db, db.begin():
        third_id = begin_run(db, db.get(Source, source_id, with_for_update=True)).id
    process_operation(third_id)
    with Session(get_engine()) as db:
        new = db.scalar(select(Job).where(Job.baseline.is_(False)))
        assert new is not None
        assert (
            db.scalar(select(JobRevision).where(JobRevision.job_id == new.id)).posting["title"]
            == "Legal adviser"
        )
        assert all(job.availability == "active" for job in db.scalars(select(Job)))


def test_generic_links_exclude_already_collected_roles_and_bound_expansion(monkeypatch):
    body = (
        html(posting())
        + '<a href="/jobs/one">Same job</a>'
        + "".join(f'<a href="/jobs/{index}">Role</a>' for index in range(201))
    )
    monkeypatch.setattr(
        generic_inventory,
        "fetch_document",
        lambda request: FetchResult(
            url=request.url, status=200, content_type="text/html", body=body
        ),
    )
    result = generic_inventory.collect("https://example.com/jobs", "Example", "https://example.com")
    assert "https://example.com/jobs/one" not in result.next_urls
    assert len(result.next_urls) == 200
    assert "generic_link_limit" in result.issues and not result.complete


def test_generic_duplicate_card_does_not_create_conflicting_revision_within_epoch():
    from app.collection.contracts import InventoryPage, Posting
    from app.collection.inventory import apply_page
    from app.collection.models import CollectionRun
    from test_inventory import source

    with Session(get_engine()) as db, db.begin():
        row = source(db)
        row.adapter = "generic_http"
        row.authoritative = False
        operation = begin_run(db, row)
        run_id = UUID(operation.parameters["run_id"])
        posted = Posting(
            external_id="one",
            title="Strategy",
            description="Full description",
            url="https://example.com/jobs/one",
            apply_url="https://example.com/jobs/one",
        )
        apply_page(
            db,
            run_id,
            0,
            InventoryPage(
                postings=[posted], complete=True, next_urls=["https://example.com/jobs/page2"]
            ),
            operation.id,
        )
        second = begin_run(db, row)
        apply_page(
            db,
            run_id,
            1,
            InventoryPage(
                postings=[posted.model_copy(update={"description": "Short card"})], complete=True
            ),
            second.id,
        )
        assert db.scalar(select(Job)).current_revision == 1
        assert db.scalar(select(JobRevision)).posting["description"] == "Full description"
        assert "unstable_pagination" in db.get(CollectionRun, run_id).issues
