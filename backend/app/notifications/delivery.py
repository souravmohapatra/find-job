"""Commit sending before I/O; retries are bounded and ambiguity never retries itself."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from app.config import get_settings
from app.db import get_engine
from app.notifications.models import Delivery, Digest, NotificationEvent, NotificationSettings
from app.notifications.transport import Outcome, message, publish, target
from app.profile_models import Operation, now
from app.services.operations import create_operation
from sqlalchemy import select, text, update
from sqlalchemy.orm import Session, aliased


def release(db: Session, digest: Digest) -> None:
    db.execute(
        update(NotificationEvent)
        .where(NotificationEvent.digest_id == digest.id)
        .values(digest_id=None)
    )


def terminal_failure(db: Session, digest: Digest | None) -> None:
    if digest is None:
        return
    uncertain = db.scalar(
        select(Delivery.id)
        .where(Delivery.digest_id == digest.id, Delivery.state == "unknown")
        .limit(1)
    )
    digest.state = "unknown" if uncertain else "failed"
    if not uncertain:
        release(db, digest)


def queue(
    db: Session, digest: Digest | None, previous: Delivery | None = None, *, manual: bool = False
) -> Delivery:
    if previous is None or manual:
        group_id, batch_attempt, destination = uuid4(), 1, target()
        deadline = (now() if manual or digest is None else digest.cutoff) + timedelta(minutes=30)
    else:
        group_id, batch_attempt, destination = (
            previous.group_id,
            previous.batch_attempt + 1,
            previous.target,
        )
        deadline = previous.deadline_at
    attempt = previous.attempt + 1 if previous else 1
    key = f"{digest.id}:{attempt}" if digest else f"test:{group_id}:{batch_attempt}"
    operation = create_operation(
        db, "digest_deliver", key, {"digest_id": str(digest.id) if digest else None}
    )
    delivery = Delivery(
        digest_id=digest.id if digest else None,
        operation_id=operation.id,
        attempt=attempt,
        group_id=group_id,
        batch_attempt=batch_attempt,
        manual=manual or digest is None or bool(previous and previous.manual),
        deadline_at=deadline,
        target=destination,
    )
    db.add(delivery)
    db.flush()
    return delivery


def reconcile_attempt(
    db: Session, digest: Digest | None, previous: Delivery | None, instant: datetime
) -> int:
    if previous and previous.state in {"sending", "sent", "unknown"}:
        return 0
    deadline = (
        previous.deadline_at
        if previous
        else digest.cutoff + timedelta(minutes=30)
        if digest
        else instant
    )
    if instant > deadline:
        if previous and previous.state in {"pending", "failed"}:
            previous.state, previous.error_code = "failed", "notification_window_expired"
            previous.retryable, previous.finished_at = False, instant
        terminal_failure(db, digest)
        return 0
    if previous is None:
        queue(db, digest)
        return 1
    if (
        previous.state == "failed"
        and previous.retryable
        and previous.batch_attempt < 3
        and previous.available_at <= instant
    ):
        queue(db, digest, previous)
        return 1
    if previous.state == "pending":
        operation = db.get(Operation, previous.operation_id)
        if operation is None or operation.state in {"failed", "blocked", "cancelled"}:
            previous.state, previous.error_code, previous.finished_at = (
                "failed",
                "notification_worker_failed",
                instant,
            )
            terminal_failure(db, digest)
    return 0


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
        digest = db.get(Digest, delivery.digest_id) if delivery.digest_id else None
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
        count += reconcile_attempt(db, digest, previous, instant)
    newer = aliased(Delivery)
    has_newer = (
        select(newer.id)
        .where(newer.group_id == Delivery.group_id, newer.batch_attempt > Delivery.batch_attempt)
        .exists()
    )
    tests = list(
        db.scalars(
            select(Delivery)
            .where(
                Delivery.digest_id.is_(None),
                Delivery.state.in_(["pending", "failed"]),
                ~has_newer,
                (Delivery.state == "pending") | Delivery.retryable.is_(True),
            )
            .order_by(Delivery.available_at)
            .limit(100)
        )
    )
    for previous in tests:
        count += reconcile_attempt(db, None, previous, instant)
    return count


def finish(db: Session, delivery: Delivery, digest: Digest | None, outcome: Outcome) -> None:
    instant = now()
    delivery.state, delivery.error_code = outcome.state, outcome.code
    delivery.remote_id, delivery.finished_at = outcome.remote_id, instant
    try:
        delivery.available_at = instant + timedelta(
            seconds=max(60 * 2 ** (delivery.batch_attempt - 1), outcome.retry_after)
        )
    except OverflowError:
        delivery.available_at = datetime.max.replace(tzinfo=UTC)
    delivery.retryable = bool(
        outcome.state == "failed"
        and outcome.retryable
        and delivery.batch_attempt < 3
        and delivery.available_at <= delivery.deadline_at
    )
    if digest:
        digest.state = "pending" if delivery.retryable else outcome.state
        if digest.state == "failed":
            terminal_failure(db, digest)


def deliver(operation_id: UUID, token: UUID, digest_id: UUID | None) -> None:
    with Session(get_engine()) as db, db.begin():
        db.execute(text("SELECT pg_advisory_xact_lock(1012001)"))
        operation = db.get(Operation, operation_id, with_for_update=True)
        delivery = db.scalar(
            select(Delivery).where(Delivery.operation_id == operation_id).with_for_update()
        )
        digest = db.get(Digest, digest_id, with_for_update=True) if digest_id else None
        if (
            operation is None
            or operation.state != "running"
            or operation.lease_token != token
            or delivery is None
            or (digest_id is not None and digest is None)
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
        if digest and (digest.state != "pending" or not digest.snapshot):
            code = "notification_cancelled"
        elif not delivery.manual and (settings is None or not settings.enabled):
            code = "notifications_disabled"
        elif digest and digest.integration_mode != get_settings().integration_mode:
            code = "notification_mode_changed"
        elif now() > delivery.deadline_at:
            code = "notification_window_expired"
        if code:
            finish(db, delivery, digest, Outcome("failed", code))
            return
        body = (
            f"Summary for {digest.local_date} ({digest.timezone}).\n"
            + message(digest.snapshot, digest.integration_mode)
            if digest
            else "This is a test notification from Job Finder. No job events were consumed."
        )
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
        if digest:
            digest.state = "sending"
        identifier = delivery.id
    try:
        outcome = publish(destination, body)
    except Exception:
        outcome = Outcome("unknown", "ntfy_unexpected_transport_failure")
    with Session(get_engine()) as db, db.begin():
        db.execute(text("SELECT pg_advisory_xact_lock(1012001)"))
        delivery = db.get(Delivery, identifier, with_for_update=True)
        digest = db.get(Digest, digest_id, with_for_update=True) if digest_id else None
        if (
            delivery is not None
            and (digest is not None or digest_id is None)
            and delivery.state == "sending"
        ):
            finish(db, delivery, digest, outcome)


def purge(db: Session) -> None:
    db.execute(
        update(Operation)
        .where(
            Operation.kind == "digest_deliver",
            Operation.state.in_(["queued", "running", "blocked"]),
        )
        .values(state="cancelled", lease_token=None)
    )
    for delivery in db.scalars(select(Delivery).where(Delivery.state.in_(["pending", "sending"]))):
        digest = db.get(Digest, delivery.digest_id) if delivery.digest_id else None
        finish(
            db,
            delivery,
            digest,
            Outcome("unknown" if delivery.state == "sending" else "failed", "profile_purged"),
        )
