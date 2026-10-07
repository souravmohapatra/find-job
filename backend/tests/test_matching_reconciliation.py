from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from app.ai.contracts import TaskConfig
from app.ai.models import TaskRevision
from app.collection.models import Job, JobRevision
from app.config import get_settings
from app.db import get_engine
from app.profile_models import Operation, Profile
from app.services import matching
from app.services.operations import OperationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_assessments import setup
from test_inventory import posting


def add_job(db, availability="active"):
    prior = db.scalar(select(JobRevision).order_by(JobRevision.id).limit(1))
    job = Job(
        company_id=db.get(Job, prior.job_id).company_id,
        canonical_key=str(uuid4()),
        availability=availability,
    )
    db.add(job)
    db.flush()
    db.add(
        JobRevision(
            job_id=job.id,
            revision=1,
            content_hash="a" * 64,
            posting=posting(description="Lead strategy").model_dump(mode="json"),
            source_id=prior.source_id,
        )
    )
    db.flush()
    return job.id


def test_policy_upgrade_batches_and_failure_does_not_repeat(monkeypatch):
    with Session(get_engine()) as db, db.begin():
        setup(db)
        add_job(db)
        add_job(db, "unknown")
        add_job(db, "closed")
    monkeypatch.setattr(matching, "POLICY_VERSION", "broad-v2")
    with Session(get_engine()) as db, db.begin():
        assert matching.reconcile(db, batch_size=2) == 2
    with Session(get_engine()) as db, db.begin():
        assert matching.reconcile(db, batch_size=2) == 1
        rows = list(
            db.scalars(
                select(Operation).where(Operation.parameters["policy_version"].astext == "broad-v2")
            )
        )
        assert len(rows) == 3
        for operation, state in zip(rows, ["failed", "blocked", "succeeded"], strict=True):
            operation.state = state
    with Session(get_engine()) as db, db.begin():
        assert matching.reconcile(db) == 0
        assert (
            db.scalar(
                select(func.count()).select_from(Operation).where(Operation.kind == "job_assess")
            )
            == 4
        )


def test_policy_rollback_fills_new_inventory_without_replaying_existing_intents(monkeypatch):
    original = matching.POLICY_VERSION
    with Session(get_engine()) as db, db.begin():
        setup(db)
    monkeypatch.setattr(matching, "POLICY_VERSION", "broad-v2")
    with Session(get_engine()) as db, db.begin():
        add_job(db)
        assert matching.reconcile(db) == 2
    monkeypatch.setattr(matching, "POLICY_VERSION", original)
    with Session(get_engine()) as db, db.begin():
        assert matching.reconcile(db) == 1
        assert matching.reconcile(db) == 0


def test_concurrent_reconciliation_and_mode_change_are_idempotent(monkeypatch):
    with Session(get_engine()) as db, db.begin():
        setup(db)
        add_job(db)

    def reconcile(_):
        with Session(get_engine()) as db, db.begin():
            return matching.reconcile(db)

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(reconcile, range(2))) == [0, 1]
    monkeypatch.setattr(get_settings(), "integration_mode", "live")
    with Session(get_engine()) as db, db.begin():
        assert matching.reconcile(db) == 2
        assert matching.reconcile(db) == 0
    # Only intents are queued; this test never executes a live model call.


def test_no_profile_or_model_skips_reconciliation_and_obsolete_fanout_stops():
    with Session(get_engine()) as db, db.begin():
        assert matching.reconcile(db) == 0
        setup(db)
        db.add(
            TaskRevision(
                task="job_matching", revision=2, config=TaskConfig().model_dump(mode="json")
            )
        )
        db.flush()
        assert matching.reconcile(db) == 0
        db.get(Profile, 1).current_revision = 99
        assert matching.reconcile(db) == 0
        with pytest.raises(OperationError) as error:
            matching.expand(db, {"policy_version": "obsolete"})
        assert error.value.code == "assessment_policy_changed"


def test_periodic_control_tick_discovers_policy_change(monkeypatch):
    from app.tasks import worker

    with Session(get_engine()) as db, db.begin():
        setup(db)
    monkeypatch.setattr(matching, "POLICY_VERSION", "broad-v-next")
    monkeypatch.setattr(worker, "dispatch", lambda: 0)
    worker.tick(0)
    with Session(get_engine()) as db:
        queued = db.scalar(
            select(Operation).where(
                Operation.kind == "job_assess",
                Operation.parameters["policy_version"].astext == "broad-v-next",
            )
        )
        assert queued is not None and queued.state == "queued"
