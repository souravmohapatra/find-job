from datetime import timedelta

import pytest
from app.db import get_engine
from app.notifications import delivery
from app.notifications.ledger import schedule
from app.notifications.models import Delivery, Digest, NotificationEvent
from app.notifications.transport import Outcome
from app.profile_models import Operation
from app.services.operations import process_operation
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_notification_ledger import CUTOFF, seed


def start(monkeypatch):
    seed(monkeypatch, baseline=False)
    clock = [CUTOFF + timedelta(seconds=10)]
    monkeypatch.setattr(delivery, "now", lambda: clock[0])
    with Session(get_engine()) as db, db.begin():
        digest_id = schedule(db, CUTOFF).id
        assert delivery.reconcile(db) == 1
        identifier = db.scalar(select(Delivery)).operation_id
    return digest_id, identifier, clock


def test_sending_committed_before_publish_and_replay_never_resends(monkeypatch):
    digest_id, identifier, _ = start(monkeypatch)
    calls = []

    def publish(target, body):
        with Session(get_engine()) as db:
            assert db.get(Digest, digest_id).state == "sending"
            assert db.scalar(select(Delivery)).state == "sending"
        assert "1 new shortlisted roles" in body and "Synthetic assessment" in body
        calls.append(target)
        return Outcome("sent", remote_id="synthetic-acceptance")

    monkeypatch.setattr(delivery, "publish", publish)
    process_operation(identifier)
    process_operation(identifier)
    with Session(get_engine()) as db:
        assert db.get(Digest, digest_id).state == "sent"
        assert db.scalar(select(Delivery)).remote_id == "synthetic-acceptance"
        assert db.scalar(select(NotificationEvent)).digest_id == digest_id
    assert len(calls) == 1


@pytest.mark.parametrize(
    "outcome,reserved",
    [(Outcome("unknown", "timeout"), True), (Outcome("failed", "rejected"), False)],
)
def test_unknown_is_held_and_definite_failure_releases_membership(monkeypatch, outcome, reserved):
    digest_id, identifier, clock = start(monkeypatch)
    monkeypatch.setattr(delivery, "publish", lambda *args: outcome)
    process_operation(identifier)
    with Session(get_engine()) as db, db.begin():
        assert db.get(Digest, digest_id).state == outcome.state
        assert (db.scalar(select(NotificationEvent)).digest_id is not None) == reserved
        clock[0] += timedelta(minutes=5)
        assert delivery.reconcile(db) == 0
        assert db.scalar(select(func.count()).select_from(Delivery)) == 1
        next_digest = schedule(db, CUTOFF + timedelta(days=1))
        assert next_digest.snapshot["counts"]["new"] == (0 if reserved else 1)


def test_definitely_unsent_retry_is_bounded_and_preserves_snapshot(monkeypatch):
    digest_id, identifier, clock = start(monkeypatch)
    monkeypatch.setattr(
        delivery, "publish", lambda *args: Outcome("failed", "connect", retryable=True)
    )
    for attempt in range(1, 4):
        process_operation(identifier)
        with Session(get_engine()) as db, db.begin():
            row = db.scalar(select(Delivery).order_by(Delivery.attempt.desc()))
            assert row.attempt == attempt and row.state == "failed"
            assert db.get(Digest, digest_id).snapshot["counts"]["new"] == 1
            if attempt < 3:
                assert delivery.reconcile(db) == 0
                clock[0] = row.available_at
                assert delivery.reconcile(db) == 1
                identifier = db.scalar(
                    select(Delivery).order_by(Delivery.attempt.desc())
                ).operation_id
            else:
                assert db.get(Digest, digest_id).state == "failed"
                assert db.scalar(select(NotificationEvent)).digest_id is None
                assert delivery.reconcile(db) == 0


def test_expired_slot_and_crashed_sending_have_different_recovery(monkeypatch):
    digest_id, identifier, clock = start(monkeypatch)
    monkeypatch.setattr(delivery, "publish", lambda *args: pytest.fail("Must not publish"))
    clock[0] = CUTOFF + timedelta(minutes=31)
    process_operation(identifier)
    with Session(get_engine()) as db, db.begin():
        row = db.scalar(select(Delivery))
        assert row.error_code == "notification_window_expired"
        # Simulate a distinct crash after sending was durably recorded.
        row.state = "sending"
        row.started_at = CUTOFF
        db.get(Digest, digest_id).state = "sending"
        assert delivery.reconcile(db) == 0
        assert row.state == "unknown" and db.get(Digest, digest_id).state == "unknown"


def test_purge_during_send_discards_content_and_keeps_outcome_unknown(monkeypatch, client):
    from test_inventory_api import auth

    digest_id, identifier, _ = start(monkeypatch)
    headers = auth(client)

    def publish(*args):
        assert (
            client.post(
                "/api/v1/profile/purge", headers=headers, json={"confirmation": "DELETE PROFILE"}
            ).status_code
            == 204
        )
        return Outcome("sent", remote_id="late-receipt")

    monkeypatch.setattr(delivery, "publish", publish)
    process_operation(identifier)
    with Session(get_engine()) as db:
        assert db.get(Digest, digest_id).snapshot == {}
        assert db.get(Digest, digest_id).state == "unknown"
        assert db.scalar(select(Delivery)).state == "unknown"
        assert db.get(Operation, identifier).state == "cancelled"


def test_mock_notification_mode_cannot_consume_a_real_delivery(monkeypatch):
    digest_id, identifier, _ = start(monkeypatch)
    process_operation(identifier)
    with Session(get_engine()) as db:
        assert db.get(Digest, digest_id).state == "failed"
        assert db.scalar(select(Delivery)).error_code == "notification_mock_mode"
        assert db.scalar(select(NotificationEvent)).digest_id is None


def test_crash_after_sending_commit_is_unknown_without_republish(monkeypatch):
    digest_id, identifier, clock = start(monkeypatch)
    with Session(get_engine()) as db, db.begin():
        row = db.scalar(select(Delivery))
        row.state, row.started_at = "sending", CUTOFF
        db.get(Digest, digest_id).state = "sending"
    monkeypatch.setattr(delivery, "publish", lambda *args: pytest.fail("No resend after a crash"))
    clock[0] += timedelta(minutes=3)
    with Session(get_engine()) as db, db.begin():
        delivery.reconcile(db)
        assert db.get(Digest, digest_id).state == "unknown"
        assert db.scalar(select(NotificationEvent)).digest_id == digest_id
    process_operation(identifier)
    with Session(get_engine()) as db:
        assert db.scalar(select(Delivery)).state == "unknown"


def test_history_exposes_safe_receipt_and_generic_retry_cannot_resend(monkeypatch, client):
    from test_inventory_api import auth

    _, identifier, _ = start(monkeypatch)
    monkeypatch.setattr(delivery, "publish", lambda *args: Outcome("unknown", "synthetic_timeout"))
    process_operation(identifier)
    headers = auth(client)
    history = client.get("/api/v1/notifications")
    assert history.status_code == 200
    result = history.json()["items"][0]["delivery"]
    assert result["state"] == "unknown" and result["error_code"] == "synthetic_timeout"
    assert "target" not in result and "token" not in result
    with Session(get_engine()) as db, db.begin():
        db.get(Operation, identifier).state = "failed"
    response = client.post(f"/api/v1/operations/{identifier}/retry", headers=headers)
    assert response.status_code == 409 and response.json()["code"] == "notification_retry_required"


def test_long_rate_limit_survives_next_digest_without_early_http(monkeypatch):
    _, identifier, clock = start(monkeypatch)
    calls = []

    def limited(*args):
        calls.append(True)
        return Outcome("failed", "ntfy_rate_limited", retryable=True, retry_after=2 * 86400)

    monkeypatch.setattr(delivery, "publish", limited)
    process_operation(identifier)
    clock[0] = CUTOFF + timedelta(days=1)
    with Session(get_engine()) as db, db.begin():
        next_digest = schedule(db, clock[0])
        delivery.reconcile(db)
        next_operation = db.scalar(
            select(Delivery).where(Delivery.digest_id == next_digest.id)
        ).operation_id
    process_operation(next_operation)
    assert calls == [True]
    with Session(get_engine()) as db:
        latest = db.scalar(select(Delivery).order_by(Delivery.available_at.desc()))
        assert latest.error_code == "ntfy_rate_limited" and latest.available_at > clock[0]
