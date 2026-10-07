from datetime import timedelta
from uuid import UUID, uuid4

from app.db import get_engine
from app.notifications import delivery
from app.notifications.ledger import schedule
from app.notifications.models import Delivery, Digest, NotificationEvent
from app.notifications.transport import Outcome
from app.services.operations import process_operation
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_inventory_api import auth
from test_notification_delivery import start
from test_notification_ledger import CUTOFF


def resend(client, headers, digest_id, expected, key=None, acknowledge=False):
    return client.post(
        f"/api/v1/notifications/{digest_id}/resend",
        headers={**headers, "Idempotency-Key": key or str(uuid4())},
        json={
            "expected_delivery_id": str(expected) if expected else None,
            "accept_possible_duplicate": acknowledge,
        },
    )


def failed(monkeypatch, state="failed"):
    digest_id, operation_id, clock = start(monkeypatch)
    monkeypatch.setattr(delivery, "publish", lambda *args: Outcome(state, "synthetic_failure"))
    process_operation(operation_id)
    with Session(get_engine()) as db:
        row = db.scalar(select(Delivery))
        return digest_id, row.id, clock


def test_explicit_resend_has_fresh_window_and_replays_original_request(monkeypatch, client):
    digest_id, previous_id, clock = failed(monkeypatch)
    clock[0] = CUTOFF + timedelta(days=2)
    headers = auth(client)
    key = str(uuid4())
    response = resend(client, headers, digest_id, previous_id, key)
    assert response.status_code == 202
    assert resend(client, headers, digest_id, previous_id, key).json() == response.json()
    identifier = UUID(response.json()["operation_id"])
    with Session(get_engine()) as db:
        row = db.scalar(select(Delivery).where(Delivery.operation_id == identifier))
        assert row.manual and row.batch_attempt == 1 and row.attempt == 2
        assert row.deadline_at == clock[0] + timedelta(minutes=30)
        assert db.get(Digest, digest_id).cutoff == CUTOFF
        assert db.scalar(select(NotificationEvent)).digest_id == digest_id
    calls = []
    monkeypatch.setattr(
        delivery,
        "publish",
        lambda *args: calls.append(args) or Outcome("sent", remote_id="manual-receipt"),
    )
    process_operation(identifier)
    assert len(calls) == 1 and "Summary for 2026-10-07" in calls[0][1]
    assert resend(client, headers, digest_id, previous_id, key).json() == response.json()
    assert resend(client, headers, digest_id, previous_id).status_code == 409
    assert len(calls) == 1


def test_unknown_requires_acknowledgement_and_remains_held_after_failed_resend(monkeypatch, client):
    digest_id, previous_id, _ = failed(monkeypatch, "unknown")
    headers = auth(client)
    assert resend(client, headers, digest_id, previous_id).status_code == 422
    response = resend(client, headers, digest_id, previous_id, acknowledge=True)
    assert response.status_code == 202
    monkeypatch.setattr(delivery, "publish", lambda *args: Outcome("failed", "definitely_rejected"))
    process_operation(UUID(response.json()["operation_id"]))
    with Session(get_engine()) as db, db.begin():
        assert db.get(Digest, digest_id).state == "unknown"
        assert db.scalar(select(NotificationEvent)).digest_id == digest_id
        assert schedule(db, CUTOFF + timedelta(days=1)).snapshot["counts"]["new"] == 0


def test_expired_manual_retry_batch_cannot_erase_original_unknown(monkeypatch, client):
    digest_id, previous_id, clock = failed(monkeypatch, "unknown")
    response = resend(client, auth(client), digest_id, previous_id, acknowledge=True)
    assert response.status_code == 202
    clock[0] += timedelta(hours=1)
    with Session(get_engine()) as db, db.begin():
        delivery.reconcile(db)
        assert db.get(Digest, digest_id).state == "unknown"
        assert db.scalar(select(NotificationEvent)).digest_id == digest_id


def test_newer_digest_membership_prevents_resending_old_failed_summary(monkeypatch, client):
    digest_id, previous_id, _ = failed(monkeypatch)
    with Session(get_engine()) as db, db.begin():
        assert schedule(db, CUTOFF + timedelta(days=1)).snapshot["counts"]["new"] == 1
    response = resend(client, auth(client), digest_id, previous_id)
    assert response.status_code == 409 and response.json()["code"] == "notification_superseded"


def test_purged_summary_cannot_be_resent(monkeypatch, client):
    digest_id, previous_id, _ = failed(monkeypatch)
    headers = auth(client)
    assert (
        client.post(
            "/api/v1/profile/purge", headers=headers, json={"confirmation": "DELETE PROFILE"}
        ).status_code
        == 204
    )
    response = resend(client, headers, digest_id, previous_id)
    assert response.status_code == 409 and response.json()["code"] == "notification_content_removed"


def test_test_message_requires_auth_and_key_and_does_not_consume_digest(monkeypatch, client):
    assert client.post("/api/v1/settings/notifications/test").status_code == 401
    headers = auth(client)
    assert client.post("/api/v1/settings/notifications/test", headers=headers).status_code == 428
    headers = {**headers, "Idempotency-Key": str(uuid4())}
    response = client.post("/api/v1/settings/notifications/test", headers=headers)
    assert response.status_code == 202
    assert (
        client.post("/api/v1/settings/notifications/test", headers=headers).json()
        == response.json()
    )
    calls = []
    monkeypatch.setattr(
        delivery,
        "publish",
        lambda *args: calls.append(args) or Outcome("sent", remote_id="test-receipt"),
    )
    process_operation(UUID(response.json()["operation_id"]))
    assert len(calls) == 1 and "test notification" in calls[0][1]
    with Session(get_engine()) as db:
        assert db.scalar(select(Digest)) is None
        assert db.scalar(select(NotificationEvent)) is None
        assert db.scalar(select(func.count()).select_from(Delivery)) == 1
    history = client.get("/api/v1/settings/notifications/tests").json()
    assert len(history) == 1 and history[0]["remote_id"] == "test-receipt"
    status = client.get(f"/api/v1/notifications/deliveries/{response.json()['resource_id']}")
    assert status.status_code == 200 and status.json()["state"] == "sent"


def test_test_message_transient_retry_shares_batch_and_stops_after_three(monkeypatch, client):
    clock = [CUTOFF]
    monkeypatch.setattr(delivery, "now", lambda: clock[0])
    response = client.post(
        "/api/v1/settings/notifications/test",
        headers={**auth(client), "Idempotency-Key": str(uuid4())},
    )
    identifier = UUID(response.json()["operation_id"])
    monkeypatch.setattr(
        delivery, "publish", lambda *args: Outcome("failed", "connect", retryable=True)
    )
    group = None
    for attempt in range(1, 4):
        process_operation(identifier)
        with Session(get_engine()) as db, db.begin():
            row = db.scalar(select(Delivery).order_by(Delivery.batch_attempt.desc()))
            group = group or row.group_id
            assert row.group_id == group and row.batch_attempt == attempt
            clock[0] = row.available_at
            assert delivery.reconcile(db) == (1 if attempt < 3 else 0)
            identifier = db.scalar(
                select(Delivery).order_by(Delivery.batch_attempt.desc())
            ).operation_id
    assert len(client.get("/api/v1/settings/notifications/tests").json()) == 1


def test_request_key_cannot_be_reused_for_different_action(monkeypatch, client):
    digest_id, previous_id, _ = failed(monkeypatch)
    headers = auth(client)
    key = str(uuid4())
    assert (
        client.post(
            "/api/v1/settings/notifications/test", headers={**headers, "Idempotency-Key": key}
        ).status_code
        == 202
    )
    assert resend(client, headers, digest_id, previous_id, key).status_code == 409
