"""Non-secret, versioned AI configuration. Models are deliberately unset initially."""

import re
from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from app.domain.profile import Contract

TaskKey = Literal["profile_analysis", "job_extraction", "job_matching"]
TASKS: tuple[TaskKey, ...] = ("profile_analysis", "job_extraction", "job_matching")


class TaskConfig(Contract):
    model: str | None = Field(default=None, max_length=200)
    # Wire protocol for this revision. Older revisions without the field keep their
    # historical chat meaning through this default; decisions is the native typed
    # Decisions endpoint. Enforced to "job_matching" only at save and dispatch time.
    protocol: Literal["chat", "decisions"] = "chat"
    fallback_models: list[str] = Field(default_factory=list, max_length=3)
    providers: list[str] = Field(default_factory=list, max_length=10)
    zdr: bool = False
    input_tokens: int = Field(default=16000, ge=1000, le=200000)
    output_tokens: int = Field(default=4000, ge=256, le=32000)
    timeout_seconds: int = Field(default=120, ge=10, le=120)
    temperature: float | None = Field(default=None, ge=0, le=2, allow_inf_nan=False)
    reasoning_effort: Literal["low", "medium", "high"] | None = None
    # Explicit routing ceilings, USD per million tokens; request fees excluded by default.
    prompt_price: Decimal = Field(default=Decimal("20"), ge=0, le=1000, decimal_places=6)
    completion_price: Decimal = Field(default=Decimal("60"), ge=0, le=1000, decimal_places=6)
    request_price: Decimal = Field(default=Decimal("0"), ge=0, le=10, decimal_places=6)

    @field_validator("model")
    @classmethod
    def model_id(cls, value: str | None) -> str | None:
        if value is not None and (
            not re.fullmatch(r"[\w.-]+/[\w.:-]+", value)
            or value.startswith("openrouter/")
            or ":" in value
            and not value.endswith(":free")
        ):
            raise ValueError("Use an explicit author/model ID; automatic routers are unsupported")
        return value

    @field_validator("fallback_models")
    @classmethod
    def fallbacks(cls, values: list[str]) -> list[str]:
        for value in values:
            cls.model_id(value)
        if len(set(values)) != len(values):
            raise ValueError("Fallback model IDs must be unique")
        return values

    @field_validator("providers")
    @classmethod
    def provider_ids(cls, values: list[str]) -> list[str]:
        if any(not re.fullmatch(r"[a-z0-9./_-]{1,100}", value) for value in values):
            raise ValueError("Use provider endpoint slugs from the OpenRouter catalog")
        return list(dict.fromkeys(values))

    @model_validator(mode="after")
    def mapping(self) -> "TaskConfig":
        if self.fallback_models and (not self.model or self.model in self.fallback_models):
            raise ValueError("Fallbacks require a distinct primary model")
        return self


class AiLimits(Contract):
    daily_calls: int = Field(default=500, ge=1, le=10000)
    daily_usd: Decimal = Field(default=Decimal("5"), gt=0, le=1000, decimal_places=6)


class TaskView(Contract):
    task: TaskKey
    revision: int
    config: TaskConfig
    validation_state: str
    error_code: str | None


class AiSettingsView(Contract):
    integration_mode: str
    key_configured: bool
    limits_revision: int
    limits: AiLimits
    tasks: list[TaskView]


class TaskUpdate(Contract):
    task: TaskKey
    config: TaskConfig


class ValidateRequest(Contract):
    task: TaskKey
    acknowledge_cost: bool = False


class VerifyCost(Contract):
    cost_usd: Decimal = Field(ge=0, le=100000, decimal_places=8)
    confirmation: Literal["I VERIFIED THE PROVIDER BILLING"]


class CallView(Contract):
    id: UUID
    task: TaskKey
    operation_id: UUID | None
    state: str
    model: str
    provider: str | None
    generation_id: str | None
    reserved_usd: Decimal
    reported_usd: Decimal | None
    cost_source: str | None
    accounted_at: datetime | None
    error_code: str | None
    created_at: datetime


class TaskUsage(Contract):
    task: TaskKey
    calls_today: int
    reported_usd: Decimal
    held_usd: Decimal
    unresolved_count: int


class UsageView(Contract):
    day_start_utc: datetime
    tasks: list[TaskUsage]
    recent: list[CallView]
    unresolved: list[CallView]
