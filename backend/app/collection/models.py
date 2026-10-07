"""Company watches and profile-independent vacancy inventory."""

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from app.db import Base
from app.profile_models import now
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column


class Company(Base):
    __tablename__ = "companies"
    __table_args__ = (CheckConstraint("interval_hours BETWEEN 1 AND 720", name="company_interval"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    label: Mapped[str] = mapped_column(String(200))
    website: Mapped[str | None] = mapped_column(String(4096))
    resolution: Mapped[str] = mapped_column(String(30), default="unresolved")
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    paused: Mapped[bool] = mapped_column(default=False)
    interval_hours: Mapped[int] = mapped_column(default=24)
    revision: Mapped[int] = mapped_column(default=1)
    discovery_due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Source(Base):
    __tablename__ = "sources"
    __table_args__ = (
        UniqueConstraint("company_id", "identity", name="uq_company_source"),
        CheckConstraint("interval_hours BETWEEN 1 AND 720", name="source_interval"),
        Index("ix_source_due", "enabled", "next_due_at"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id"), index=True)
    identity: Mapped[str] = mapped_column(String(64))
    adapter: Mapped[str] = mapped_column(String(30))
    config: Mapped[dict[str, Any]] = mapped_column(JSONB)
    url: Mapped[str] = mapped_column(String(4096))
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    authoritative: Mapped[bool] = mapped_column(default=True)
    enabled: Mapped[bool] = mapped_column(default=True)
    interval_hours: Mapped[int] = mapped_column(default=24)
    revision: Mapped[int] = mapped_column(default=1)
    next_due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    cooldown_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    baseline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(100))


class CollectionRun(Base):
    __tablename__ = "collection_runs"
    __table_args__ = (
        CheckConstraint(
            "state IN ('collecting','complete','partial','failed','expired','cancelled')",
            name="collection_state",
        ),
        Index("ix_collection_source_state", "source_id", "state"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    source_id: Mapped[UUID] = mapped_column(ForeignKey("sources.id"))
    source_revision: Mapped[int]
    state: Mapped[str] = mapped_column(String(20), default="collecting")
    next_offset: Mapped[int] = mapped_column(default=0)
    frontier: Mapped[list[str]] = mapped_column(JSONB, default=list)
    pages: Mapped[int] = mapped_column(default=0)
    issues: Mapped[list[str]] = mapped_column(JSONB, default=list)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint("company_id", "canonical_key", name="uq_company_job_identity"),
        CheckConstraint("availability IN ('active','closed','unknown')", name="job_availability"),
        Index("ix_jobs_company_seen", "company_id", "first_seen_at", "id"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id"))
    canonical_key: Mapped[str] = mapped_column(String(64))
    current_revision: Mapped[int] = mapped_column(default=1)
    availability: Mapped[str] = mapped_column(String(20), default="active")
    baseline: Mapped[bool] = mapped_column(default=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class JobRevision(Base):
    __tablename__ = "job_revisions"
    __table_args__ = (UniqueConstraint("job_id", "revision", name="uq_job_revision"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    job_id: Mapped[UUID] = mapped_column(ForeignKey("jobs.id"), index=True)
    revision: Mapped[int]
    content_hash: Mapped[str] = mapped_column(String(64))
    posting: Mapped[dict[str, Any]] = mapped_column(JSONB)
    source_id: Mapped[UUID] = mapped_column(ForeignKey("sources.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class JobSource(Base):
    __tablename__ = "job_sources"
    __table_args__ = (
        UniqueConstraint("source_id", "external_key", name="uq_source_posting"),
        CheckConstraint("omissions >= 0", name="nonnegative_omissions"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    job_id: Mapped[UUID] = mapped_column(ForeignKey("jobs.id"), index=True)
    source_id: Mapped[UUID] = mapped_column(ForeignKey("sources.id"))
    external_key: Mapped[str] = mapped_column(String(64))
    external_id: Mapped[str] = mapped_column(String(4096))
    omissions: Mapped[int] = mapped_column(default=0)
    available: Mapped[bool] = mapped_column(default=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Observation(Base):
    __tablename__ = "collection_observations"
    run_id: Mapped[UUID] = mapped_column(ForeignKey("collection_runs.id"), primary_key=True)
    association_id: Mapped[UUID] = mapped_column(ForeignKey("job_sources.id"), primary_key=True)


class CollectionPage(Base):
    __tablename__ = "collection_pages"
    run_id: Mapped[UUID] = mapped_column(ForeignKey("collection_runs.id"), primary_key=True)
    offset: Mapped[int] = mapped_column(primary_key=True)
    operation_id: Mapped[UUID] = mapped_column(ForeignKey("operation_intents.id"), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class DiscoveryRun(Base):
    __tablename__ = "discovery_runs"
    __table_args__ = (
        Index("ix_discovery_company_state", "company_id", "state"),
        CheckConstraint(
            "state IN ('running','complete','partial','cancelled','expired')",
            name="discovery_state",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id"))
    company_revision: Mapped[int]
    state: Mapped[str] = mapped_column(String(20), default="running")
    frontier: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    cursor: Mapped[int] = mapped_column(default=0)
    issues: Mapped[list[str]] = mapped_column(JSONB, default=list)
    candidates: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SearchRequest(Base):
    __tablename__ = "search_requests"
    __table_args__ = (
        UniqueConstraint("run_id", "slot", name="uq_search_run_slot"),
        Index("ix_search_requested_at", "requested_at"),
        CheckConstraint("slot BETWEEN 0 AND 2", name="search_slot"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(ForeignKey("discovery_runs.id"))
    slot: Mapped[int]
    query: Mapped[str] = mapped_column(String(1000))
    state: Mapped[str] = mapped_column(String(20), default="reserved")
    results: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    error_code: Mapped[str | None] = mapped_column(String(100))
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class SearchState(Base):
    __tablename__ = "search_state"
    id: Mapped[int] = mapped_column(primary_key=True)
    next_allowed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
