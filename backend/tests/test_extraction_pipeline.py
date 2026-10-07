from datetime import timedelta
from uuid import uuid4

import pytest
from app.ai.contracts import TaskConfig
from app.ai.extraction import ExtractedJob, Extraction
from app.ai.models import TaskRevision
from app.collection import discovery, extraction, generic_inventory
from app.collection.inventory import begin_run
from app.collection.models import (
    CollectionPage,
    CollectionRun,
    Company,
    Job,
    PageExtraction,
    Source,
)
from app.config import get_settings
from app.db import get_engine
from app.domain.profile import Evidence
from app.fetcher.contracts import FetchResult
from app.profile_models import Operation, now
from app.services.operations import OperationError, process_operation
from sqlalchemy import func, select
from sqlalchemy.orm import Session

HTML = (
    "<h1>Example careers</h1><h2>Strategy planner</h2><p>Hiring now</p>"
    "<p>Lead strategy projects.</p><p>Other employer</p>"
)


def response(status="open", employer="Example"):
    def quote(value):
        return Evidence(span_id="s1", quote=value)

    return Extraction(
        coverage="detail",
        jobs=[
            ExtractedJob(
                title=quote("Strategy planner"),
                employer=quote(employer),
                description=[quote("Lead strategy projects.")],
                vacancy_evidence=[quote("Hiring now")],
                link_id="source",
                status=status,
            )
        ],
    )


def setup(monkeypatch, mapped=True):
    fetches = []

    def fetch(request):
        fetches.append(request.url)
        return FetchResult(url=request.url, status=200, content_type="text/html", body=HTML)

    monkeypatch.setattr(generic_inventory, "fetch_document", fetch)
    with Session(get_engine()) as db, db.begin():
        if mapped:
            db.add(
                TaskRevision(
                    task="job_extraction",
                    revision=1,
                    config=TaskConfig(model="example/extraction").model_dump(mode="json"),
                )
            )
        company = Company(label="Example", website="https://example.com")
        db.add(company)
        db.flush()
        source = Source(
            company_id=company.id,
            identity="e" * 64,
            adapter="generic_http",
            authoritative=False,
            url="https://example.com/careers",
            config={"company_name": "Example", "website": company.website},
        )
        db.add(source)
        db.flush()
        source_id = source.id
        operation = begin_run(db, source)
        fetch_id = operation.id
    process_operation(fetch_id)
    with Session(get_engine()) as db:
        snapshot = db.scalar(select(PageExtraction))
        assert snapshot and snapshot.payload["text"]
        assert db.scalar(select(Job)) is None
        return source_id, snapshot.run_id, snapshot.operation_id, fetches


def test_page_snapshot_crosses_ai_queue_once_and_saves_verified_open_job(monkeypatch):
    source_id, run_id, identifier, fetches = setup(monkeypatch)
    calls = []

    def infer(text, source_url, links, config_id, operation_id):
        assert "Lead strategy projects." in text and source_url.endswith("/careers")
        assert config_id is not None and operation_id == identifier
        calls.append(True)
        return response()

    monkeypatch.setattr(extraction, "extract", infer)
    with Session(get_engine()) as db, db.begin():
        assert begin_run(db, db.get(Source, source_id)).id == identifier
    process_operation(identifier)
    process_operation(identifier)
    assert len(fetches) == len(calls) == 1
    with Session(get_engine()) as db:
        assert db.scalar(select(Job)).baseline is True
        assert db.get(CollectionRun, run_id).state == "partial"
        assert db.get(PageExtraction, (run_id, 0)).result
        assert db.get(CollectionPage, (run_id, 0)).operation_id == identifier
        assert db.get(Source, source_id).baseline_at is not None


@pytest.mark.parametrize(
    "status,employer,issue",
    [
        ("closed", "Example", "extracted_job_not_confirmed_open"),
        ("uncertain", "Example", "extracted_job_not_confirmed_open"),
        ("open", "Other employer", "job_employer_unverified"),
    ],
)
def test_only_open_attributed_jobs_enter_inventory(monkeypatch, status, employer, issue):
    _, run_id, identifier, _ = setup(monkeypatch)
    monkeypatch.setattr(extraction, "extract", lambda *args: response(status, employer))
    process_operation(identifier)
    with Session(get_engine()) as db:
        assert db.scalar(select(Job)) is None
        assert issue in db.get(CollectionRun, run_id).issues
        assert db.get(CollectionRun, run_id).state == "partial"


def test_failed_extraction_can_retry_same_snapshot_without_refetch(monkeypatch, client):
    from test_inventory_api import auth

    _, run_id, identifier, fetches = setup(monkeypatch)

    def fail(*args):
        raise OperationError("synthetic_unavailable", "Synthetic failure")

    monkeypatch.setattr(extraction, "extract", fail)
    process_operation(identifier)
    with Session(get_engine()) as db:
        assert db.get(CollectionRun, run_id).state == "failed"
    headers = auth(client)
    assert client.post(f"/api/v1/operations/{identifier}/retry", headers=headers).status_code == 202
    monkeypatch.setattr(extraction, "extract", lambda *args: response())
    process_operation(identifier)
    with Session(get_engine()) as db:
        assert db.scalar(select(Job)) is not None
        assert db.get(Operation, identifier).state == "succeeded"
    assert len(fetches) == 1


@pytest.mark.parametrize("change", ["source", "new_run", "mode", "lease"])
def test_obsolete_or_lost_lease_results_never_publish(monkeypatch, change):
    source_id, run_id, identifier, _ = setup(monkeypatch)

    def infer(*args):
        with Session(get_engine()) as db, db.begin():
            if change == "source":
                db.get(Source, source_id).revision += 1
            elif change == "new_run":
                db.get(CollectionRun, run_id).state = "failed"
                begin_run(db, db.get(Source, source_id))
            elif change == "lease":
                db.get(Operation, identifier).lease_token = uuid4()
        if change == "mode":
            monkeypatch.setattr(get_settings(), "integration_mode", "live")
        return response()

    monkeypatch.setattr(extraction, "extract", infer)
    process_operation(identifier)
    with Session(get_engine()) as db:
        assert db.scalar(select(Job)) is None
        assert db.get(PageExtraction, (run_id, 0)).result is None


def test_missing_model_can_be_mapped_on_explicit_retry_and_old_snapshots_expire(
    monkeypatch, client
):
    from app.services.retention import expire_page_extractions
    from test_inventory_api import auth

    _, run_id, identifier, fetches = setup(monkeypatch, mapped=False)
    process_operation(identifier)
    with Session(get_engine()) as db, db.begin():
        assert db.get(Operation, identifier).error_code == "configuration_required"
        db.add(
            TaskRevision(
                task="job_extraction",
                revision=1,
                config=TaskConfig(model="example/extraction").model_dump(mode="json"),
            )
        )
    headers = auth(client)
    assert client.post(f"/api/v1/operations/{identifier}/retry", headers=headers).status_code == 202

    def infer(*args):
        assert args[3] is not None
        return response()

    monkeypatch.setattr(extraction, "extract", infer)
    process_operation(identifier)
    assert len(fetches) == 1
    with Session(get_engine()) as db, db.begin():
        db.get(PageExtraction, (run_id, 0)).created_at = now() - timedelta(days=8)
    assert expire_page_extractions() == 1
    with Session(get_engine()) as db:
        assert db.scalar(select(func.count()).select_from(Job)) == 1
        assert db.get(Operation, identifier).state == "succeeded"


def test_plain_official_careers_page_is_source_but_not_verified_vacancy(monkeypatch):
    monkeypatch.setattr(
        discovery,
        "fetch_document",
        lambda request: FetchResult(
            url=request.url, status=200, content_type="text/html", body=HTML
        ),
    )
    with Session(get_engine()) as db, db.begin():
        company = Company(label="Example", website="https://example.com/careers")
        db.add(company)
        db.flush()
        identifier = discovery.begin(db, company).id
    process_operation(identifier)
    with Session(get_engine()) as db:
        source = db.scalar(select(Source))
        assert source.adapter == "generic_http" and not source.authoritative
        assert source.evidence["jobs_verified"] is False
        assert db.scalar(select(Job)) is None


def test_oversized_page_remains_partial_without_truncated_ai_input(monkeypatch):
    monkeypatch.setattr(
        generic_inventory,
        "fetch_document",
        lambda request: FetchResult(
            url=request.url, status=200, content_type="text/html", body="<p>" + "x" * 40001 + "</p>"
        ),
    )
    page = generic_inventory.collect(
        "https://example.com/careers", "Example", "https://example.com"
    )
    assert not page.complete and not page.postings
    assert "extraction_input_limit" in page.issues
    assert getattr(page, "extraction", None) is None


def test_ai_completion_advances_persisted_frontier(monkeypatch):
    from app.collection.extraction_input import PublicPage

    source_id, run_id, identifier, fetches = setup(monkeypatch)
    with Session(get_engine()) as db, db.begin():
        snapshot = db.get(PageExtraction, (run_id, 0))
        snapshot.inventory = {
            **snapshot.inventory,
            "next_urls": ["https://example.com/jobs/detail"],
        }
    monkeypatch.setattr(extraction, "extract", lambda *args: Extraction(coverage="uncertain"))
    process_operation(identifier)
    with Session(get_engine()) as db, db.begin():
        run = db.get(CollectionRun, run_id)
        assert run.next_offset == 1 and run.pages == 1 and run.state == "collecting"
        next_operation = begin_run(db, db.get(Source, source_id))
        assert next_operation.kind == "source_collect"
        next_id = next_operation.id
    process_operation(next_id)
    with Session(get_engine()) as db:
        snapshot = db.get(PageExtraction, (run_id, 1))
        assert PublicPage.model_validate(snapshot.payload).url.endswith("/jobs/detail")
        next_ai = snapshot.operation_id
    process_operation(next_ai)
    with Session(get_engine()) as db:
        run = db.get(CollectionRun, run_id)
        assert run.pages == 2 and run.state == "partial"
    assert len(fetches) == 2
