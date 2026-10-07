"""AI configuration and content-free request accounting."""

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from app.db import Base
from app.profile_models import now
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column


class AiLimitsRow(Base):
    __tablename__ = "ai_limits"
    __table_args__ = (CheckConstraint("id = 1", name="single_ai_limits"),)
    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    revision: Mapped[int] = mapped_column(default=0)
    settings: Mapped[dict[str, Any]] = mapped_column(JSONB)


class TaskRevision(Base):
    __tablename__ = "ai_task_revisions"
    __table_args__ = (UniqueConstraint("task", "revision", name="uq_ai_task_revision"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    task: Mapped[str] = mapped_column(String(40), index=True)
    revision: Mapped[int]
    config: Mapped[dict[str, Any]] = mapped_column(JSONB)
    prompt_version: Mapped[str] = mapped_column(String(40), default="v1")
    schema_version: Mapped[str] = mapped_column(String(40), default="v1")
    validation_state: Mapped[str] = mapped_column(String(30), default="unvalidated")
    error_code: Mapped[str | None] = mapped_column(String(80))
    cooldown_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class InferenceCall(Base):
    __tablename__ = "inference_calls"
    __table_args__ = (
        CheckConstraint("reserved_usd >= 0", name="nonnegative_ai_reservation"),
        CheckConstraint("reported_usd IS NULL OR reported_usd >= 0", name="nonnegative_ai_cost"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    operation_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("operation_intents.id", ondelete="SET NULL")
    )
    config_id: Mapped[UUID] = mapped_column(ForeignKey("ai_task_revisions.id"))
    task: Mapped[str] = mapped_column(String(40), index=True)
    requested_model: Mapped[str] = mapped_column(String(200))
    returned_model: Mapped[str | None] = mapped_column(String(200))
    provider: Mapped[str | None] = mapped_column(String(200))
    generation_id: Mapped[str | None] = mapped_column(String(200))
    prompt_version: Mapped[str] = mapped_column(String(40))
    schema_version: Mapped[str] = mapped_column(String(40))
    state: Mapped[str] = mapped_column(String(30), default="reserved", index=True)
    error_code: Mapped[str | None] = mapped_column(String(80))
    reserved_usd: Mapped[Decimal] = mapped_column(Numeric(16, 8))
    reported_usd: Mapped[Decimal | None] = mapped_column(Numeric(16, 8))
    prompt_tokens: Mapped[int | None]
    completion_tokens: Mapped[int | None]
    latency_ms: Mapped[int | None]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
