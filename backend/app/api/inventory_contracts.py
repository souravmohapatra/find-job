from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from app.collection.contracts import Adapter, Posting, public_link
from pydantic import BaseModel, ConfigDict, Field, field_validator


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class CompanyInput(Input):
    label: str = Field(min_length=1, max_length=200)
    website: str | None = None
    interval_hours: int = Field(default=24, ge=1, le=720)

    @field_validator("website")
    @classmethod
    def website_url(cls, value: str | None) -> str | None:
        return public_link(value) if value else None


class CompanyEdit(CompanyInput):
    paused: bool = False


class CompanyView(CompanyEdit):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    revision: int
    resolution: str
    created_at: datetime


class CompanyPage(BaseModel):
    items: list[CompanyView]
    next_offset: int | None


class SourceInput(Input):
    adapter: Adapter
    board: str = Field(pattern=r"^[A-Za-z0-9_-]{1,200}$")
    region: Literal["global", "eu"] = "global"
    confirmed_company: Literal[True]
    interval_hours: int | None = Field(default=None, ge=1, le=720)


class SourceEdit(Input):
    enabled: bool
    interval_hours: int = Field(ge=1, le=720)


class SourceView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    company_id: UUID
    adapter: str
    url: str
    revision: int
    enabled: bool
    interval_hours: int
    next_due_at: datetime
    cooldown_until: datetime | None
    baseline_at: datetime | None
    last_success_at: datetime | None
    last_error: str | None


class RunView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    state: str
    pages: int
    issues: list[str]
    started_at: datetime
    finished_at: datetime | None


class JobView(BaseModel):
    id: UUID
    company_id: UUID
    company_label: str
    revision_id: UUID
    revision: int
    availability: str
    baseline: bool
    first_seen_at: datetime
    last_seen_at: datetime
    posting: Posting
    assessment_status: Literal["not_assessed"] = "not_assessed"


class JobPage(BaseModel):
    items: list[JobView]
    next_cursor: str | None
    matching_available: bool = False


class JobDetail(JobView):
    sources: list[SourceView]
    revision_count: int


Availability = Literal["all", "active", "closed", "unknown"]
PageSize = Annotated[int, Field(ge=1, le=100)]


class DiscoveryCandidate(BaseModel):
    url: str
    title: str
    employer: str | None
    source_url: str
    evidence_path: str
    status: str


class DiscoveryView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    state: str
    cursor: int
    issues: list[str]
    candidates: list[DiscoveryCandidate]
    started_at: datetime
    finished_at: datetime | None
