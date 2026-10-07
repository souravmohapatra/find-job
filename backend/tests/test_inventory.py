from datetime import timedelta
from uuid import UUID

from app.collection.contracts import InventoryPage, Posting
from app.collection.inventory import apply_page, begin_run, key, schedule_due
from app.collection.models import CollectionRun, Company, Job, JobRevision, JobSource, Source
from app.db import get_engine
from app.profile_models import Operation, now
from sqlalchemy import func, select
from sqlalchemy.orm import Session


def source(db: Session, *, company_id: UUID | None = None, board: str = "synthetic") -> Source:
    if company_id is None:
        company = Company(label="Synthetic company")
        db.add(company)
        db.flush()
        company_id = company.id
    row = Source(
        company_id=company_id,
        identity=key(board),
        adapter="lever",
        config={"board": board},
        url=f"https://jobs.lever.co/{board}",
    )
    db.add(row)
    db.flush()
    return row


def posting(identifier: str = "a", *, description: str = "Lead planning.") -> Posting:
    return Posting(
        external_id=identifier,
        title="Strategy role",
        description=description,
        url=f"https://careers.example.com/{identifier}",
        apply_url=f"https://careers.example.com/{identifier}/apply",
    )


def collect(db: Session, row: Source, page: InventoryPage) -> CollectionRun:
    operation = begin_run(db, row)
    assert operation is not None
    run_id = UUID(operation.parameters["run_id"])
    apply_page(db, run_id, operation.parameters["offset"], page, operation.id)
    db.flush()
    return db.get(CollectionRun, run_id)


def test_durable_pages_replay_and_closure_only_after_three_complete_omissions() -> None:
    with Session(get_engine()) as db, db.begin():
        row = source(db)
        first = collect(db, row, InventoryPage(postings=[posting()], complete=True))
        job = db.scalar(select(Job))
        assert first.state == "complete" and row.baseline_at is not None and job.baseline
        empty = InventoryPage(postings=[], complete=True)
        collect(db, row, empty)
        assert db.scalar(select(JobSource)).omissions == 1
        partial = collect(
            db, row, InventoryPage(postings=[], complete=False, issues=["invalid_posting"])
        )
        assert partial.state == "partial" and db.scalar(select(JobSource)).omissions == 1
        run = collect(
            db, row, InventoryPage(postings=[posting("b")], complete=False, next_offset=100)
        )
        run_id, source_id, job_id = run.id, row.id, job.id
        assert db.scalar(select(JobSource).where(JobSource.job_id == job_id)).omissions == 1
    # A fresh DB session represents continuation after worker/process restart.
    with Session(get_engine()) as db, db.begin():
        row = db.get(Source, source_id, with_for_update=True)
        operation = begin_run(db, row)
        assert (
            UUID(operation.parameters["run_id"]) == run_id and operation.parameters["offset"] == 100
        )
        apply_page(db, run_id, 100, empty, operation.id)
        apply_page(db, run_id, 100, empty, operation.id)  # Redelivery cannot count omissions twice.
        db.flush()
        association = db.scalar(select(JobSource).where(JobSource.job_id == job_id))
        assert association.omissions == 2
        collect(db, row, empty)
        assert db.get(Job, job_id).availability == "closed"
        collect(
            db,
            row,
            InventoryPage(postings=[posting(description="Lead global planning.")], complete=True),
        )
        assert db.get(Job, job_id).availability == "active" and association.omissions == 0
        assert db.get(Job, job_id).current_revision == 2
        assert (
            db.scalar(
                select(func.count()).select_from(JobRevision).where(JobRevision.job_id == job_id)
            )
            == 2
        )
        assert db.scalar(select(Job).where(Job.id != job_id)).baseline is False


def test_cross_source_merge_needs_identical_url_and_all_sources_must_close() -> None:
    with Session(get_engine()) as db, db.begin():
        one = source(db)
        two = source(db, company_id=one.company_id, board="other")
        collect(db, one, InventoryPage(postings=[posting()], complete=True))
        collect(
            db,
            two,
            InventoryPage(
                postings=[posting().model_copy(update={"external_id": "other-id"})], complete=True
            ),
        )
        assert db.scalar(select(func.count()).select_from(Job)) == 1
        assert db.scalar(select(func.count()).select_from(JobSource)) == 2
        for _ in range(3):
            collect(db, one, InventoryPage(postings=[], complete=True))
        assert db.scalar(select(Job)).availability == "active"
        two.authoritative = False
        for _ in range(3):
            collect(db, two, InventoryPage(postings=[], complete=True))
        assert db.scalar(select(Job)).availability == "active"
        collect(db, two, InventoryPage(postings=[posting("different-url")], complete=True))
        assert db.scalar(select(func.count()).select_from(Job)) == 2  # Same title is not identity.


def test_unstable_pagination_and_expired_epoch_never_close_missing_jobs() -> None:
    with Session(get_engine()) as db, db.begin():
        row = source(db)
        collect(db, row, InventoryPage(postings=[posting("missing")], complete=True))
        run = collect(db, row, InventoryPage(postings=[posting()], complete=False, next_offset=100))
        operation = begin_run(db, row)
        apply_page(
            db, run.id, 100, InventoryPage(postings=[posting()], complete=True), operation.id
        )
        db.flush()
        assert run.state == "partial" and "unstable_pagination" in run.issues
        missing = db.scalar(select(JobSource).where(JobSource.external_id == "missing"))
        assert missing.omissions == 0
        run = collect(db, row, InventoryPage(postings=[], complete=False, next_offset=100))
        run.started_at = now() - timedelta(hours=25)
        db.flush()
        replacement = begin_run(db, row)
        assert run.state == "expired" and str(run.id) != replacement.parameters["run_id"]
        assert missing.omissions == 0


def test_schedule_catches_up_once_respects_pause_cooldown_and_rejects_stale_source() -> None:
    with Session(get_engine()) as db, db.begin():
        row = source(db)
        row.next_due_at = now() - timedelta(days=10)
        assert schedule_due(db) == 1
        db.flush()
        assert schedule_due(db) == 0
        assert row.next_due_at > now() + timedelta(hours=23)
        op = db.scalar(select(Operation).where(Operation.kind == "source_collect"))
        row.revision += 1
        apply_page(
            db,
            UUID(op.parameters["run_id"]),
            0,
            InventoryPage(postings=[posting()], complete=True),
            op.id,
        )
        assert db.scalar(select(func.count()).select_from(Job)) == 0
        row.next_due_at = now() - timedelta(hours=1)
        row.cooldown_until = now() + timedelta(hours=1)
        assert schedule_due(db) == 0
        row.cooldown_until = None
        db.get(Company, row.company_id).paused = True
        db.flush()
        assert schedule_due(db) == 0


def test_worker_collection_is_idempotent_and_missing_fetcher_is_visible(monkeypatch) -> None:
    from app.collection import runner
    from app.services.operations import process_operation

    with Session(get_engine()) as db, db.begin():
        row = source(db)
        operation = begin_run(db, row)
        operation_id, source_id = operation.id, row.id
    process_operation(operation_id)
    with Session(get_engine()) as db:
        assert db.get(Operation, operation_id).state == "blocked"
        assert db.get(Source, source_id).last_error == "fetcher_unavailable"
        assert db.scalar(select(CollectionRun)).state == "failed"
        assert db.scalar(select(Job)) is None
    calls = []

    def fetch(url):
        calls.append(url)
        return [
            {
                "id": "a",
                "text": "Strategy role",
                "descriptionPlain": "Lead planning.",
                "hostedUrl": "https://jobs.lever.co/synthetic/a",
                "applyUrl": "https://jobs.lever.co/synthetic/a/apply",
            }
        ]

    monkeypatch.setattr(runner, "fetch_json", fetch)
    with Session(get_engine()) as db, db.begin():
        operation_id = begin_run(db, db.get(Source, source_id, with_for_update=True)).id
    process_operation(operation_id)
    process_operation(operation_id)
    with Session(get_engine()) as db:
        assert db.get(Operation, operation_id).state == "succeeded"
        assert db.scalar(select(func.count()).select_from(Job)) == 1
        assert db.get(Source, source_id).last_error is None
    assert len(calls) == 1


def test_lost_worker_lease_cannot_publish_fetched_jobs(monkeypatch) -> None:
    from uuid import uuid4

    from app.collection import runner
    from app.services.operations import process_operation

    with Session(get_engine()) as db, db.begin():
        operation_id = begin_run(db, source(db)).id

    def fetch(url):
        with Session(get_engine()) as other, other.begin():
            other.get(Operation, operation_id, with_for_update=True).lease_token = uuid4()
        return [
            {
                "id": "a",
                "text": "Strategy role",
                "descriptionPlain": "Lead planning.",
                "hostedUrl": "https://jobs.lever.co/synthetic/a",
                "applyUrl": "https://jobs.lever.co/synthetic/a/apply",
            }
        ]

    monkeypatch.setattr(runner, "fetch_json", fetch)
    process_operation(operation_id)
    with Session(get_engine()) as db:
        assert db.scalar(select(Job)) is None
        assert db.get(Operation, operation_id).state == "running"
        assert db.scalar(select(CollectionRun)).pages == 0


def test_concurrent_schedulers_create_one_catchup() -> None:
    from concurrent.futures import ThreadPoolExecutor

    with Session(get_engine()) as db, db.begin():
        source(db)

    def schedule():
        with Session(get_engine()) as db, db.begin():
            return schedule_due(db)

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sum(executor.map(lambda _: schedule(), range(2))) == 1
    with Session(get_engine()) as db:
        assert db.scalar(select(func.count()).select_from(CollectionRun)) == 1
        assert db.scalar(select(func.count()).select_from(Operation)) == 1


def test_transient_fetch_failure_preserves_inventory_and_retries_with_cooldown(monkeypatch) -> None:
    from app.collection import runner
    from app.services.operations import OperationError, process_operation

    with Session(get_engine()) as db, db.begin():
        row = source(db)
        collect(db, row, InventoryPage(postings=[posting()], complete=True))
        operation_id = begin_run(db, row).id
        source_id = row.id

    def unavailable(url):
        raise OperationError(
            "source_rate_limited", "Source requested a delay.", retryable=True, retry_after=120
        )

    monkeypatch.setattr(runner, "fetch_json", unavailable)
    process_operation(operation_id)
    with Session(get_engine()) as db, db.begin():
        operation = db.get(Operation, operation_id)
        assert operation.state == "queued" and operation.available_at > now() + timedelta(
            seconds=110
        )
        assert db.get(Source, source_id).cooldown_until > now() + timedelta(seconds=110)
        assert db.scalar(select(JobSource)).omissions == 0
        assert db.scalar(select(Job)).availability == "active"
        assert db.get(CollectionRun, UUID(operation.parameters["run_id"])).state == "collecting"
        # An obsolete result must not overwrite newer source state.
        row = db.get(Source, source_id)
        row.revision += 1
        row.last_error = None
        runner.record_failure(
            db, UUID(operation.parameters["run_id"]), "old_failure", terminal=True, retry_after=None
        )
        assert row.last_error is None
        assert db.get(CollectionRun, UUID(operation.parameters["run_id"])).state == "cancelled"
