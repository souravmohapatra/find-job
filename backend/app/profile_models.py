from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def now() -> datetime:
    return datetime.now(UTC)


class Profile(Base):
    __tablename__ = "profiles"
    __table_args__ = (
        CheckConstraint("id = 1", name="single_profile"),
        CheckConstraint("current_revision >= 0", name="nonnegative_profile_revision"),
    )
    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    current_revision: Mapped[int] = mapped_column(default=0)


class ProfileRevision(Base):
    __tablename__ = "profile_revisions"
    __table_args__ = (UniqueConstraint("profile_id", "revision", name="uq_profile_revision"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    profile_id: Mapped[int] = mapped_column(ForeignKey("profiles.id"), default=1)
    revision: Mapped[int]
    facts: Mapped[dict[str, Any]] = mapped_column(JSONB)
    preferences: Mapped[dict[str, Any]] = mapped_column(JSONB)
    schema_version: Mapped[int] = mapped_column(default=1)
    author: Mapped[str] = mapped_column(String(20), default="owner")
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (CheckConstraint("size > 0 AND size <= 10485760", name="document_size_limit"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    storage_key: Mapped[str] = mapped_column(String(100), unique=True)
    media_type: Mapped[str] = mapped_column(String(100))
    size: Mapped[int]
    sha256: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(30), default="queued")
    spans: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    retain_original: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ProfileDraft(Base):
    __tablename__ = "profile_drafts"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    document_id: Mapped[UUID] = mapped_column(ForeignKey("documents.id"), unique=True)
    base_revision: Mapped[int]
    version: Mapped[int] = mapped_column(default=1)
    status: Mapped[str] = mapped_column(String(30), default="processing")
    facts: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    preferences: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Operation(Base):
    __tablename__ = "operation_intents"
    __table_args__ = (
        CheckConstraint(
            "state IN ('queued','running','blocked','succeeded','failed','cancelled')",
            name="operation_state",
        ),
        CheckConstraint("attempts >= 0", name="operation_attempts"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    kind: Mapped[str] = mapped_column(String(50))
    dedupe_key: Mapped[str] = mapped_column(String(200), unique=True)
    request_hash: Mapped[str] = mapped_column(String(64))
    parameters: Mapped[dict[str, Any]] = mapped_column(JSONB)
    state: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    progress: Mapped[str] = mapped_column(String(300), default="Waiting to start")
    error_code: Mapped[str | None] = mapped_column(String(80))
    error_message: Mapped[str | None] = mapped_column(String(500))
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_token: Mapped[UUID | None]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
