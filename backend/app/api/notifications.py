"""Owner-only schedule configuration and inspectable immutable digest history."""

from datetime import date
from typing import Annotated

from app.api.ai import check_revision
from app.api.profiles import Expected
from app.auth import DB, Auth
from app.notifications.contracts import (
    DigestHistory,
    DigestSnapshot,
    DigestView,
    NotificationPreferences,
    NotificationSettingsView,
)
from app.notifications.ledger import advance
from app.notifications.models import Digest, NotificationSettings
from app.profile_models import now
from fastapi import APIRouter, Query, Response
from sqlalchemy import select, text

router = APIRouter(tags=["notifications"])


def view(row: NotificationSettings | None) -> NotificationSettingsView:
    if row is None:
        return NotificationSettingsView(revision=0, next_date=None, next_due_at=None)
    return NotificationSettingsView(
        revision=row.revision,
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
    return DigestHistory(
        items=[
            DigestView(
                id=row.id,
                local_date=row.local_date,
                cutoff=row.cutoff,
                timezone=row.timezone,
                local_time=row.local_time,
                integration_mode=row.integration_mode,
                state=row.state,
                snapshot=DigestSnapshot.model_validate(row.snapshot),
                created_at=row.created_at,
            )
            for row in rows[:limit]
        ],
        next_before=rows[limit - 1].local_date if len(rows) > limit else None,
    )
