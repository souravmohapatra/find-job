"""Commit sending before I/O; retries are bounded and ambiguity never retries itself."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from app.config import get_settings
from app.db import get_engine
from app.notifications.models import Delivery, Digest, NotificationEvent, NotificationSettings
from app.notifications.transport import Outcome, message, publish, target
from app.profile_models import Operation, now
from app.services.operations import create_operation
from sqlalchemy import select, text, update
from sqlalchemy.orm import Session


def release(db: Session, digest: Digest) -> None:
    db.execute(
        update(NotificationEvent)
        .where(NotificationEvent.digest_id == digest.id)
        .values(digest_id=None)
    )


def queue(db: Session, digest: Digest, previous: Delivery | None = None) -> Delivery:
    attempt = previous.attempt + 1 if previous else 1
    operation = create_operation(
        db, "digest_deliver", f"{digest.id}:{attempt}", {"digest_id": str(digest.id)}
    )
    delivery = Delivery(
        digest_id=digest.id,
        operation_id=operation.id,
        attempt=attempt,
        target=previous.target if previous else target(),
    )
    db.add(delivery)
    db.flush()
    return delivery


def reconcile(db: Session, instant: datetime | None = None) -> int:
    instant = instant or now()
    db.execute(text("SELECT pg_advisory_xact_lock(1012001)"))
    abandoned = db.scalars(
        select(Delivery)
        .where(Delivery.state == "sending", Delivery.started_at < instant - timedelta(minutes=2))
        .limit(100)
    )
    for delivery in abandoned:
        delivery.state, delivery.error_code, delivery.finished_at = (
            "unknown",
            "ntfy_worker_interrupted",
            instant,
        )
        digest = db.get(Digest, delivery.digest_id)
        if digest:
            digest.state = "unknown"
    count = 0
    digests = list(
        db.scalars(
            select(Digest).where(Digest.state == "pending").order_by(Digest.cutoff).limit(100)
        )
    )
    for digest in digests:
        previous = db.scalar(
            select(Delivery)
            .where(Delivery.digest_id == digest.id)
            .order_by(Delivery.attempt.desc())
            .limit(1)
        )
        if previous and previous.state == "sending":
            continue
        if instant > digest.cutoff + timedelta(minutes=30):
            digest.state = "failed"
            if previous and previous.state in {"pending", "failed"}:
                previous.state, previous.error_code = "failed", "notification_window_expired"
                previous.retryable = False
                previous.finished_at = instant
            release(db, digest)
            continue
        if previous is None:
            queue(db, digest)
            count += 1
        elif (
            previous.state == "failed"
            and previous.retryable
            and previous.attempt < 3
            and previous.available_at <= instant
        ):
            queue(db, digest, previous)
            count += 1
        elif previous.state == "pending":
            operation = db.get(Operation, previous.operation_id)
            if operation is None or operation.state in {"failed", "blocked", "cancelled"}:
                previous.state, previous.error_code, previous.finished_at = (
                    "failed",
                    "notification_worker_failed",
                    instant,
                )
                digest.state = "failed"
                release(db, digest)
    return count


def finish(db: Session, delivery: Delivery, digest: Digest, outcome: Outcome) -> None:
    instant = now()
    delivery.state, delivery.error_code = outcome.state, outcome.code
    delivery.remote_id, delivery.finished_at = outcome.remote_id, instant
    try:
        delivery.available_at = instant + timedelta(
            seconds=max(60 * 2 ** (delivery.attempt - 1), outcome.retry_after)
        )
    except OverflowError:
        delivery.available_at = datetime.max.replace(tzinfo=UTC)
    delivery.retryable = bool(
        outcome.state == "failed"
        and outcome.retryable
        and delivery.attempt < 3
        and delivery.available_at <= digest.cutoff + timedelta(minutes=30)
    )
    digest.state = "pending" if delivery.retryable else outcome.state
    if digest.state == "failed":
        release(db, digest)


def deliver(operation_id: UUID, token: UUID, digest_id: UUID) -> None:
    with Session(get_engine()) as db, db.begin():
        db.execute(text("SELECT pg_advisory_xact_lock(1012001)"))
        operation = db.get(Operation, operation_id, with_for_update=True)
        delivery = db.scalar(
            select(Delivery).where(Delivery.operation_id == operation_id).with_for_update()
        )
        digest = db.get(Digest, digest_id, with_for_update=True)
        if (
            operation is None
            or operation.state != "running"
            or operation.lease_token != token
            or delivery is None
            or digest is None
            or delivery.digest_id != digest_id
        ):
            return
        if delivery.state == "sending":
            finish(db, delivery, digest, Outcome("unknown", "ntfy_worker_interrupted"))
            return
        if delivery.state != "pending":
            return
        settings = db.get(NotificationSettings, 1)
        code = None
        if digest.state != "pending" or not digest.snapshot:
            code = "notification_cancelled"
        elif settings is None or not settings.enabled:
            code = "notifications_disabled"
        elif digest.integration_mode != get_settings().integration_mode:
            code = "notification_mode_changed"
        elif now() > digest.cutoff + timedelta(minutes=30):
            code = "notification_window_expired"
        if code:
            finish(db, delivery, digest, Outcome("failed", code))
            return
        body = message(digest.snapshot, digest.integration_mode)
        destination = dict(delivery.target)
        cooldown = db.scalar(
            select(Delivery.available_at)
            .where(
                Delivery.error_code == "ntfy_rate_limited",
                Delivery.target == destination,
                Delivery.available_at > now(),
            )
            .order_by(Delivery.available_at.desc())
            .limit(1)
        )
        if cooldown is not None:
            finish(
                db,
                delivery,
                digest,
                Outcome(
                    "failed",
                    "ntfy_rate_limited",
                    retryable=True,
                    retry_after=int((cooldown - now()).total_seconds()) + 1,
                ),
            )
            return
        delivery.state, delivery.started_at = "sending", now()
        digest.state = "sending"
        identifier = delivery.id
    # No transaction or global lock spans the network request. A concurrent purge
    # can cancel later work but cannot recall a request already dispatched.
    try:
        outcome = publish(destination, body)
    except Exception:
        outcome = Outcome("unknown", "ntfy_unexpected_transport_failure")
    with Session(get_engine()) as db, db.begin():
        db.execute(text("SELECT pg_advisory_xact_lock(1012001)"))
        delivery = db.get(Delivery, identifier, with_for_update=True)
        digest = db.get(Digest, digest_id, with_for_update=True)
        if delivery is not None and digest is not None and delivery.state == "sending":
            finish(db, delivery, digest, outcome)


def purge(db: Session) -> None:
    """Erase no message here: content lives only in the parent digest snapshot."""
    db.execute(
        update(Operation)
        .where(
            Operation.kind == "digest_deliver",
            Operation.state.in_(["queued", "running", "blocked"]),
        )
        .values(state="cancelled", lease_token=None)
    )
    pending = db.scalars(select(Delivery).where(Delivery.state.in_(["pending", "sending"])))
    for delivery in pending:
        digest = db.get(Digest, delivery.digest_id)
        if digest:
            outcome = Outcome(
                "unknown" if delivery.state == "sending" else "failed", "profile_purged"
            )
            finish(db, delivery, digest, outcome)
