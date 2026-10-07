from datetime import UTC, datetime, timedelta

import pytest
from app.collection.models import Company, Job, JobAssessment, Source
from app.config import get_settings
from app.db import get_engine
from app.notifications.ledger import schedule
from app.notifications.models import Digest, DigestItem, NotificationEvent, NotificationSettings
from app.profile_models import Operation, Profile
from app.services import matching
from app.services.operations import process_operation
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_assessments import setup
from test_matching import assessment

CUTOFF = datetime(2026, 10, 7, 18, tzinfo=UTC)


def seed(monkeypatch, *, baseline=True, score=30):
    monkeypatch.setattr(
        matching, "assess", lambda *args: assessment().model_copy(update={"relevance_score": score})
    )
    with Session(get_engine()) as db, db.begin():
        _, _, identifier = setup(db)
        db.scalar(select(Job)).baseline = baseline
        db.add(
            NotificationSettings(
                id=1,
                enabled=True,
                next_date=CUTOFF.date(),
                next_due_at=CUTOFF,
            )
        )
    process_operation(identifier)
    process_operation(identifier)
    with Session(get_engine()) as db, db.begin():
        result = db.scalar(select(JobAssessment))
        result.created_at = CUTOFF - timedelta(hours=1)
        event = db.scalar(select(NotificationEvent))
        if event:
            event.created_at = result.created_at
    return identifier


@pytest.mark.parametrize("baseline,score,kind", [(True, 30, "baseline"), (False, 70, "new")])
def test_assessment_and_event_commit_once_and_daily_digest_reserves_it(
    monkeypatch, baseline, score, kind
):
    seed(monkeypatch, baseline=baseline, score=score)
    with Session(get_engine()) as db, db.begin():
        assert db.scalar(select(func.count()).select_from(NotificationEvent)) == 1
        digest = schedule(db, CUTOFF + timedelta(seconds=20))
        assert digest.snapshot["counts"][kind] == 1
        assert len(digest.snapshot["examples"]) == 1
        identifier = digest.id
        assert schedule(db, CUTOFF + timedelta(seconds=30)) is None
    with Session(get_engine()) as db, db.begin():
        assert db.scalar(select(NotificationEvent)).digest_id == identifier
        assert db.scalar(select(func.count()).select_from(DigestItem)) == 1
        assert schedule(db, CUTOFF + timedelta(days=1)).snapshot["counts"][kind] == 0


def test_late_assessment_rolls_to_next_scheduled_digest(monkeypatch):
    seed(monkeypatch, baseline=False)
    with Session(get_engine()) as db, db.begin():
        db.scalar(select(NotificationEvent)).created_at = CUTOFF + timedelta(seconds=1)
        db.scalar(select(JobAssessment)).created_at = CUTOFF + timedelta(seconds=1)
        assert schedule(db, CUTOFF + timedelta(seconds=20)).snapshot["counts"]["new"] == 0
        db.flush()
        assert db.scalar(select(NotificationEvent)).digest_id is None
        assert schedule(db, CUTOFF + timedelta(days=1)).snapshot["counts"]["new"] == 1


@pytest.mark.parametrize("change", ["profile", "job", "closed", "paused", "mode", "policy"])
def test_snapshot_rechecks_current_eligibility(monkeypatch, change):
    seed(monkeypatch)
    with Session(get_engine()) as db, db.begin():
        if change == "profile":
            db.get(Profile, 1).current_revision += 1
        elif change == "job":
            db.scalar(select(Job)).current_revision += 1
        elif change == "closed":
            db.scalar(select(Job)).availability = "closed"
        elif change == "paused":
            db.scalar(select(Company)).paused = True
        elif change == "mode":
            monkeypatch.setattr(get_settings(), "integration_mode", "live")
        else:
            db.scalar(select(JobAssessment)).policy_version = "obsolete"
        digest = schedule(db, CUTOFF)
        assert sum(digest.snapshot["counts"].values()) == 0
        assert db.scalar(select(NotificationEvent)).digest_id is None


def test_offline_slot_skips_send_and_carries_event(monkeypatch):
    seed(monkeypatch, baseline=False)
    with Session(get_engine()) as db, db.begin():
        assert schedule(db, CUTOFF + timedelta(minutes=2)) is None
        assert db.scalar(select(Digest)) is None
        assert db.scalar(select(NotificationEvent)).digest_id is None
        assert schedule(db, CUTOFF + timedelta(days=1)).snapshot["counts"]["new"] == 1


def test_empty_option_does_not_hide_source_failures(monkeypatch):
    seed(monkeypatch, score=10)
    with Session(get_engine()) as db, db.begin():
        assert db.scalar(select(NotificationEvent)) is None
        for operation in db.scalars(select(Operation).where(Operation.state == "queued")):
            operation.state = "succeeded"
        db.get(NotificationSettings, 1).include_empty = False
        assert schedule(db, CUTOFF).state == "skipped"
        db.scalar(select(Source)).last_error = "collection_failed"
        digest = schedule(db, CUTOFF + timedelta(days=1))
        assert digest.state == "pending" and digest.snapshot["source_errors"] == 1


def test_profile_purge_erases_digest_content_but_retains_daily_receipt(monkeypatch, client):
    from test_inventory_api import auth

    seed(monkeypatch)
    with Session(get_engine()) as db, db.begin():
        identifier = schedule(db, CUTOFF).id
    response = client.post(
        "/api/v1/profile/purge", headers=auth(client), json={"confirmation": "DELETE PROFILE"}
    )
    assert response.status_code == 204
    with Session(get_engine()) as db, db.begin():
        digest = db.get(Digest, identifier)
        assert digest.snapshot == {} and digest.state == "skipped"
        assert digest.profile_revision_id is None
        assert db.scalar(select(NotificationEvent)) is None
        assert db.scalar(select(DigestItem)) is None
        settings = db.get(NotificationSettings, 1)
        settings.next_due_at, settings.next_date = CUTOFF, CUTOFF.date()
        assert schedule(db, CUTOFF) is None


@pytest.mark.parametrize(
    "first_score,state,expected",
    [(10, "sent", 1), (30, "sent", 0), (30, "unknown", 0), (30, "pending", 0), (30, "failed", 1)],
)
def test_reassessment_only_notifies_newly_qualifying_unsent_roles(
    monkeypatch, first_score, state, expected
):
    from app.ai.models import TaskRevision

    seed(monkeypatch, baseline=False, score=first_score)
    with Session(get_engine()) as db, db.begin():
        schedule(db, CUTOFF).state = state
        original = db.scalar(select(TaskRevision))
        config = TaskRevision(task="job_matching", revision=2, config=original.config)
        db.add(config)
        db.flush()
        matching.expand(db, {})
        operation = db.scalar(
            select(Operation).where(
                Operation.kind == "job_assess",
                Operation.parameters["config_id"].astext == str(config.id),
            )
        )
        identifier = operation.id
    monkeypatch.setattr(
        matching, "assess", lambda *args: assessment().model_copy(update={"relevance_score": 70})
    )
    process_operation(identifier)
    with Session(get_engine()) as db, db.begin():
        event = db.scalar(select(NotificationEvent).where(NotificationEvent.digest_id.is_(None)))
        event.created_at = CUTOFF + timedelta(hours=1)
        db.get(JobAssessment, event.assessment_id).created_at = event.created_at
        digest = schedule(db, CUTOFF + timedelta(days=1))
        assert digest.snapshot["counts"] == {"new": 0, "baseline": 0, "reassessment": expected}


def test_all_events_belong_to_digest_even_when_only_ten_titles_are_shown(monkeypatch):
    from app.collection.models import JobRevision
    from app.notifications.ledger import record
    from app.services.operations import create_operation

    seed(monkeypatch, baseline=False)
    with Session(get_engine()) as db, db.begin():
        original = db.scalar(select(JobAssessment))
        revision = db.scalar(select(JobRevision))
        company_id = db.scalar(select(Job)).company_id
        for index in range(11):
            job = Job(company_id=company_id, canonical_key=f"extra-{index}", baseline=False)
            db.add(job)
            db.flush()
            extra_revision = JobRevision(
                job_id=job.id,
                revision=1,
                content_hash="x" * 64,
                posting={**revision.posting, "title": f"Synthetic role {index}"},
                source_id=revision.source_id,
            )
            db.add(extra_revision)
            db.flush()
            op = create_operation(db, "job_assess", f"extra-{index}", {})
            op.state = "succeeded"
            result = JobAssessment(
                job_revision_id=extra_revision.id,
                profile_revision_id=original.profile_revision_id,
                config_id=original.config_id,
                policy_version=original.policy_version,
                integration_mode="mock",
                category="possible_match",
                report=original.report,
                operation_id=op.id,
                created_at=CUTOFF - timedelta(minutes=1),
            )
            db.add(result)
            db.flush()
            record(db, result)
        digest = schedule(db, CUTOFF)
        assert digest.snapshot["counts"]["new"] == 12
        assert len(digest.snapshot["examples"]) == 10
        db.flush()
        assert db.scalar(select(func.count()).select_from(DigestItem)) == 12


def test_concurrent_ticks_only_snapshot_once(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor

    seed(monkeypatch)

    def tick():
        with Session(get_engine()) as db, db.begin():
            result = schedule(db, CUTOFF)
            return result.id if result else None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: tick(), range(2)))
    assert sum(result is not None for result in results) == 1
    with Session(get_engine()) as db:
        assert db.scalar(select(func.count()).select_from(Digest)) == 1


def test_settings_versioning_timezone_validation_and_history(monkeypatch, client):
    from test_inventory_api import auth

    assert client.get("/api/v1/settings/notifications").status_code == 401
    headers = auth(client)
    current = client.get("/api/v1/settings/notifications")
    assert current.json()["local_time"] == "19:00" and current.json()["revision"] == 0
    payload = {
        "enabled": True,
        "timezone": "Asia/Kolkata",
        "local_time": "18:30",
        "include_empty": True,
    }
    response = client.patch(
        "/api/v1/settings/notifications", headers={**headers, "If-Match": '"0"'}, json=payload
    )
    assert response.status_code == 200 and response.json()["next_due_at"] is not None
    due = response.json()["next_due_at"]
    assert (
        client.patch(
            "/api/v1/settings/notifications", headers={**headers, "If-Match": '"0"'}, json=payload
        ).status_code
        == 409
    )
    assert (
        client.patch(
            "/api/v1/settings/notifications",
            headers={**headers, "If-Match": '"1"'},
            json={**payload, "timezone": "Not/AZone"},
        ).status_code
        == 422
    )
    response = client.patch(
        "/api/v1/settings/notifications",
        headers={**headers, "If-Match": '"1"'},
        json={**payload, "include_empty": False},
    )
    assert response.status_code == 200 and response.json()["next_due_at"] == due
    with Session(get_engine()) as db, db.begin():
        settings = db.get(NotificationSettings, 1)
        schedule(db, settings.next_due_at)
        schedule(db, settings.next_due_at)
    history = client.get("/api/v1/notifications?limit=1").json()
    assert len(history["items"]) == 1 and history["next_before"]
    older = client.get("/api/v1/notifications", params={"before": history["next_before"]}).json()
    assert len(older["items"]) == 1 and older["next_before"] is None


def test_regular_control_tick_creates_due_digest(monkeypatch):
    from app.notifications import ledger
    from app.tasks import worker

    seed(monkeypatch)
    monkeypatch.setattr(ledger, "now", lambda: CUTOFF)
    monkeypatch.setattr(worker, "dispatch", lambda: 0)
    worker.tick(int(CUTOFF.timestamp()))
    with Session(get_engine()) as db:
        digest = db.scalar(select(Digest))
        assert digest and digest.snapshot["counts"]["baseline"] == 1


def test_current_assessment_failures_and_unresolved_watches_are_not_zero_results(monkeypatch):
    identifier = seed(monkeypatch, score=10)
    with Session(get_engine()) as db, db.begin():
        for operation in db.scalars(select(Operation).where(Operation.state == "queued")):
            operation.state = "succeeded"
        db.get(Operation, identifier).state = "failed"
        db.add(Company(label="Unresolved synthetic watch"))
        db.get(NotificationSettings, 1).include_empty = False
        digest = schedule(db, CUTOFF)
        assert digest.state == "pending"
        assert digest.snapshot["assessment_errors"] == 1
        assert digest.snapshot["unresolved_companies"] == 1
        assert sum(digest.snapshot["counts"].values()) == 0
        # A failure tied to an old policy must not remain a current assessment error.
        operation = db.get(Operation, identifier)
        operation.dedupe_key += ":obsolete"
        digest = schedule(db, CUTOFF + timedelta(days=1))
        assert digest.snapshot["assessment_errors"] == 0
