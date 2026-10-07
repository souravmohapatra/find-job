from datetime import datetime
from typing import Literal
from uuid import UUID

from app.domain.profile import Facts, Preferences, Span
from pydantic import BaseModel


class ExperienceSummary(BaseModel):
    minimum_years: float
    maximum_years: float | None
    basis: Literal["user_override", "date_union", "incomplete_dates"]


class ProfileSnapshot(BaseModel):
    revision: int
    revision_id: UUID | None
    facts: Facts
    preferences: Preferences
    experience: ExperienceSummary | None


class DraftSummary(BaseModel):
    operation_id: UUID | None
    id: UUID
    status: str
    document_id: UUID
    created_at: datetime


class ProfileView(ProfileSnapshot):
    drafts: list[DraftSummary]


class DraftView(BaseModel):
    operation_id: UUID | None
    id: UUID
    document_id: UUID
    status: str
    version: int
    base_revision: int
    facts: Facts
    preferences: Preferences
    base_profile: ProfileSnapshot
    spans: list[Span] | None


class OperationAccepted(BaseModel):
    operation_id: UUID
    resource_id: UUID
    status_url: str


class OperationView(BaseModel):
    id: UUID
    kind: str
    state: Literal["queued", "running", "blocked", "succeeded", "failed", "cancelled"]
    progress: str
    attempts: int
    error_code: str | None
    error_message: str | None
    created_at: datetime
    finished_at: datetime | None
