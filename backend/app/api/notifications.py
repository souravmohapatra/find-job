"""Owner-only schedule configuration and inspectable immutable digest history."""

from datetime import date
from typing import Annotated
from uuid import UUID

from app.api.ai import check_revision
from app.api.contracts import OperationAccepted
from app.api.profiles import Expected, Key
from app.auth import DB, Auth
from app.config import get_settings
from app.errors import problem
from app.notifications.contracts import (
    DeliveryView,
    DigestHistory,
    DigestSnapshot,
    DigestView,
    NotificationPreferences,
    NotificationSettingsView,
    ResendRequest,
)
from app.notifications.ledger import advance
from app.notifications.models import Delivery, Digest, NotificationSettings
from app.notifications.transport import origin
from app.profile_models import Operation, now
from fastapi import APIRouter, Query, Response
from sqlalchemy import func, select, text
from sqlalchemy.orm import aliased

router = APIRouter(tags=["notifications"])


def view(row: NotificationSettings | None) -> NotificationSettingsView:
    config = get_settings()
    ready = bool(
        config.ntfy_url
        and origin(config.ntfy_url)
        and config.notification_app_url
        and origin(config.notification_app_url)
        and config.ntfy_token_file.is_file()
    )
    if row is None:
        return NotificationSettingsView(
            revision=0,
            next_date=None,
            next_due_at=None,
            delivery_mode=config.notification_mode,
            publisher_configured=ready,
        )
    return NotificationSettingsView(
        revision=row.revision,
        delivery_mode=config.notification_mode,
        publisher_configured=ready,
        enabled=row.enabled,
        timezone=row.timezone,
        local_time=row.local_time,
        include_empty=row.include_empty,
        next_date=row.next_date,
        next_due_at=row.next_due_at,
    )


@router.get("/settings/notifications", response_model=NotificationSettingsView)
def get_notifications(session: Auth, db: DB, response: Response) -> NotificationSettingsView:
    result = view(db.get(NotificationSettings, 1))
    response.headers["ETag"] = f'"{result.revision}"'
    return result


@router.patch("/settings/notifications", response_model=NotificationSettingsView)
def update_notifications(
    body: NotificationPreferences,
    session: Auth,
    db: DB,
    response: Response,
    if_match: Expected = None,
) -> NotificationSettingsView:
    db.execute(text("SELECT pg_advisory_xact_lock(1012001)"))
    row = db.get(NotificationSettings, 1, with_for_update=True)
    check_revision(if_match, row.revision if row else 0)
    reschedule = row is None or (row.enabled, row.timezone, row.local_time) != (
        body.enabled,
        body.timezone,
        body.local_time,
    )
    if row is None:
        row = NotificationSettings(id=1, revision=0)
        db.add(row)
    for key, value in body.model_dump().items():
        setattr(row, key, value)
    row.revision += 1
    if not row.enabled:
        row.next_date, row.next_due_at = None, None
    elif reschedule:
        advance(row, now())
    db.commit()
    response.headers["ETag"] = f'"{row.revision}"'
    return view(row)


@router.get("/notifications", response_model=DigestHistory)
def history(
    session: Auth,
    db: DB,
    before: date | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
) -> DigestHistory:
    query = select(Digest)
    if before is not None:
        query = query.where(Digest.local_date < before)
    rows = list(db.scalars(query.order_by(Digest.local_date.desc()).limit(limit + 1)))
    prior = aliased(Delivery)
    latest_attempt = (
        select(func.max(prior.attempt))
        .where(prior.digest_id == Delivery.digest_id)
        .scalar_subquery()
    )
    deliveries = {
        item.digest_id: item
        for item in db.scalars(
            select(Delivery)
            .where(Delivery.digest_id.in_([row.id for row in rows[:limit]]))
            .where(Delivery.attempt == latest_attempt)
        )
    }
    return DigestHistory(
        items=[
            DigestView(
                content_removed=not bool(row.snapshot),
                id=row.id,
                local_date=row.local_date,
                cutoff=row.cutoff,
                timezone=row.timezone,
                local_time=row.local_time,
                integration_mode=row.integration_mode,
                state=row.state,
                snapshot=DigestSnapshot.model_validate(row.snapshot),
                created_at=row.created_at,
                delivery=DeliveryView.model_validate(deliveries[row.id], from_attributes=True)
                if row.id in deliveries
                else None,
            )
            for row in rows[:limit]
        ],
        next_before=rows[limit - 1].local_date if len(rows) > limit else None,
    )


@router.post("/notifications/{digest_id}/resend", response_model=OperationAccepted, status_code=202)
def resend(
    digest_id: UUID,
    body: ResendRequest,
    session: Auth,
    db: DB,
    idempotency_key: Key = None,
) -> dict[str, str]:
    from app.notifications.actions import request

    result = request(
        db, idempotency_key, digest_id, body.expected_delivery_id, body.accept_possible_duplicate
    )
    db.commit()
    return result


@router.post("/settings/notifications/test", response_model=OperationAccepted, status_code=202)
def test_notification(session: Auth, db: DB, idempotency_key: Key = None) -> dict[str, str]:
    from app.notifications.actions import request

    result = request(db, idempotency_key)
    db.commit()
    return result


@router.get("/settings/notifications/tests", response_model=list[DeliveryView])
def recent_tests(session: Auth, db: DB) -> list[DeliveryView]:
    prior = aliased(Delivery)
    latest_batch = (
        select(func.max(prior.batch_attempt))
        .where(prior.group_id == Delivery.group_id)
        .scalar_subquery()
    )
    rows = db.scalars(
        select(Delivery)
        .join(Operation, Operation.id == Delivery.operation_id)
        .where(
            Delivery.digest_id.is_(None),
            Delivery.batch_attempt == latest_batch,
        )
        .order_by(Operation.created_at.desc(), Delivery.id)
        .limit(20)
    )
    return [DeliveryView.model_validate(row, from_attributes=True) for row in rows]


@router.get("/notifications/deliveries/{delivery_id}", response_model=DeliveryView)
def delivery_status(delivery_id: UUID, session: Auth, db: DB) -> DeliveryView:
    row = db.get(Delivery, delivery_id)
    if row is None:
        raise problem(404, "delivery_not_found", "This delivery could not be found.")
    return DeliveryView.model_validate(row, from_attributes=True)
