"""Explicit owner commands with durable replay receipts and duplicate acknowledgement."""

from typing import Any
from uuid import UUID

from app.config import get_settings
from app.errors import problem
from app.notifications.delivery import queue
from app.notifications.models import Delivery, Digest, DigestItem, NotificationEvent
from app.profile_models import Operation, now
from app.services.operations import create_operation, operation_response
from sqlalchemy import select, text, update
from sqlalchemy.orm import Session


def request(
    db: Session,
    key: str | None,
    digest_id: UUID | None = None,
    expected_delivery_id: UUID | None = None,
    accept_possible_duplicate: bool = False,
) -> dict[str, str]:
    if not key:
        raise problem(
            428,
            "idempotency_key_required",
            "Use a request key so a network retry cannot send twice.",
        )
    db.execute(text("SELECT pg_advisory_xact_lock(1012001)"))
    payload: dict[str, Any] = {
        "digest_id": str(digest_id) if digest_id else None,
        "expected_delivery_id": str(expected_delivery_id) if expected_delivery_id else None,
        "accept_possible_duplicate": accept_possible_duplicate,
    }
    receipt = create_operation(db, "notification_action_request", key, payload)
    if receipt.state == "succeeded":
        operation = db.get(Operation, UUID(receipt.parameters["delivery_operation_id"]))
        assert operation is not None
        return operation_response(operation, UUID(receipt.parameters["delivery_id"]))
    digest = db.get(Digest, digest_id, with_for_update=True) if digest_id else None
    previous = None
    if digest_id:
        if digest is None:
            raise problem(404, "digest_not_found", "This summary could not be found.")
        previous = db.scalar(
            select(Delivery)
            .where(Delivery.digest_id == digest_id)
            .order_by(Delivery.attempt.desc())
            .limit(1)
        )
        if (previous.id if previous else None) != expected_delivery_id:
            raise problem(
                409,
                "notification_changed",
                "Delivery changed. Review its latest state before resending.",
            )
        if digest.state not in {"failed", "unknown"}:
            raise problem(
                409,
                "notification_not_resendable",
                "Only failed or unknown summaries can be resent.",
            )
        if digest.state == "unknown" and not accept_possible_duplicate:
            raise problem(
                422,
                "duplicate_acknowledgement_required",
                "The original may have arrived. Acknowledge that resending could duplicate it.",
            )
        if not digest.snapshot:
            raise problem(
                409,
                "notification_content_removed",
                "This summary's profile-derived content was removed.",
            )
        if digest.integration_mode != get_settings().integration_mode:
            raise problem(
                409,
                "notification_mode_changed",
                "This summary belongs to a different assessment mode.",
            )
        member_jobs = (
            select(NotificationEvent.job_id)
            .join(DigestItem, DigestItem.event_id == NotificationEvent.id)
            .where(DigestItem.digest_id == digest_id)
        )
        elsewhere = db.scalar(
            select(NotificationEvent.id)
            .join(Digest, Digest.id == NotificationEvent.digest_id)
            .where(
                NotificationEvent.job_id.in_(member_jobs),
                Digest.id != digest_id,
                Digest.integration_mode == digest.integration_mode,
                Digest.state.in_(["pending", "sending", "sent", "unknown"]),
            )
            .limit(1)
        )
        if elsewhere:
            raise problem(
                409,
                "notification_superseded",
                "These roles are already reserved or included in another summary.",
            )
        db.execute(
            update(NotificationEvent)
            .where(
                NotificationEvent.id.in_(
                    select(DigestItem.event_id).where(DigestItem.digest_id == digest_id)
                )
            )
            .values(digest_id=digest_id)
        )
        digest.state = "pending"
    delivery = queue(db, digest, previous, manual=True)
    receipt.parameters = {
        **payload,
        "delivery_id": str(delivery.id),
        "delivery_operation_id": str(delivery.operation_id),
    }
    receipt.state, receipt.finished_at, receipt.progress = (
        "succeeded",
        now(),
        "Notification request recorded",
    )
    operation = db.get(Operation, delivery.operation_id)
    assert operation is not None
    return operation_response(operation, delivery.id)
