from datetime import date, datetime
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.domain.profile import Contract
from pydantic import Field, field_validator


class NotificationPreferences(Contract):
    enabled: bool = False
    timezone: str = Field(default="Europe/London", min_length=1, max_length=100)
    local_time: str = Field(default="19:00", pattern=r"^([01][0-9]|2[0-3]):[0-5][0-9]$")
    include_empty: bool = True

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("Choose an IANA timezone, such as Europe/London.") from None
        return value


class NotificationSettingsView(NotificationPreferences):
    revision: int
    next_due_at: datetime | None
    next_date: date | None


class Counts(Contract):
    new: int = 0
    baseline: int = 0
    reassessment: int = 0


class CompanyCount(Contract):
    label: str
    count: int


class Example(Contract):
    job_id: UUID
    title: str
    company: str
    kind: Literal["new", "baseline", "reassessment"]
    category: Literal["match", "possible_match"]


class DigestSnapshot(Contract):
    counts: Counts = Field(default_factory=Counts)
    companies: dict[str, CompanyCount] = Field(default_factory=dict)
    examples: list[Example] = Field(default_factory=list)
    source_errors: int = 0
    pending_operations: int = 0
    assessment_errors: int = 0
    unresolved_companies: int = 0
    matching_available: bool = False


class DeliveryView(Contract):
    id: UUID
    attempt: int
    state: Literal["pending", "sending", "sent", "failed", "unknown"]
    retryable: bool
    error_code: str | None
    remote_id: str | None
    available_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class DigestView(Contract):
    id: UUID
    local_date: date
    cutoff: datetime
    timezone: str
    local_time: str
    integration_mode: str
    state: Literal["pending", "sending", "sent", "failed", "unknown", "skipped"]
    snapshot: DigestSnapshot
    created_at: datetime
    delivery: DeliveryView | None = None


class DigestHistory(Contract):
    items: list[DigestView]
    next_before: date | None
