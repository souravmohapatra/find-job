"""Durable owner schedule, eligibility events and immutable digest membership."""

from datetime import date, datetime
from typing import Any
from uuid import UUID, uuid4

from app.db import Base
from app.profile_models import now
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column


class NotificationSettings(Base):
    __tablename__ = "notification_settings"
    __table_args__ = (CheckConstraint("id = 1", name="single_notification_owner"),)
    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    revision: Mapped[int] = mapped_column(default=1)
    enabled: Mapped[bool] = mapped_column(default=False)
    timezone: Mapped[str] = mapped_column(String(100), default="Europe/London")
    local_time: Mapped[str] = mapped_column(String(5), default="19:00")
    include_empty: Mapped[bool] = mapped_column(default=True)
    next_date: Mapped[date | None]
    next_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Digest(Base):
    __tablename__ = "notification_digests"
    __table_args__ = (
        CheckConstraint(
            "state IN ('pending','sending','sent','failed','unknown','skipped')",
            name="digest_state",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    local_date: Mapped[date] = mapped_column(unique=True)
    cutoff: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    timezone: Mapped[str] = mapped_column(String(100))
    local_time: Mapped[str] = mapped_column(String(5))
    settings_revision: Mapped[int]
    profile_revision_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("profile_revisions.id", ondelete="SET NULL")
    )
    integration_mode: Mapped[str] = mapped_column(String(10))
    state: Mapped[str] = mapped_column(String(20), default="pending")
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class NotificationEvent(Base):
    __tablename__ = "notification_events"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('new','baseline','reassessment')", name="notification_event_kind"
        ),
        Index("ix_notification_pending", "digest_id", "created_at"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    assessment_id: Mapped[UUID] = mapped_column(
        ForeignKey("job_assessments.id", ondelete="CASCADE"), unique=True
    )
    job_id: Mapped[UUID] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    digest_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("notification_digests.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class DigestItem(Base):
    __tablename__ = "notification_digest_items"
    digest_id: Mapped[UUID] = mapped_column(
        ForeignKey("notification_digests.id", ondelete="CASCADE"), primary_key=True
    )
    event_id: Mapped[UUID] = mapped_column(
        ForeignKey("notification_events.id", ondelete="CASCADE"), primary_key=True
    )
