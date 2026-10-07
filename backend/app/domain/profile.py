"""Profession-neutral profile contracts and conservative experience calculations."""

import calendar
import re
from datetime import date
from math import ceil, floor
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Span(Contract):
    id: str
    text: str
    page: int | None = None
    paragraph: int | None = None


class Evidence(Contract):
    span_id: str
    quote: str = Field(min_length=1, max_length=1000)


class Fact(Contract):
    value: str = Field(min_length=1, max_length=2000)
    origin: Literal["extracted", "inferred", "user"] = "user"
    evidence: list[Evidence] = Field(default_factory=list, max_length=20)


class Employment(Contract):
    employer: str = Field(max_length=200)
    title: str = Field(max_length=200)
    start: str | None = None
    end: str | None = None
    ongoing: bool = False
    responsibilities: list[Fact] = Field(default_factory=list, max_length=50)
    evidence: list[Evidence] = Field(default_factory=list, max_length=20)
    origin: Literal["extracted", "inferred", "user"] = "user"

    @field_validator("start", "end")
    @classmethod
    def valid_date(cls, value: str | None) -> str | None:
        if value is not None:
            date_bounds(value)
        return value

    @model_validator(mode="after")
    def date_order(self) -> "Employment":
        if self.ongoing and self.end:
            raise ValueError("An ongoing role cannot also have an end date")
        if self.start and self.end and date_bounds(self.start)[0] > date_bounds(self.end)[1]:
            raise ValueError("Role end must not precede its start")
        return self


class Facts(Contract):
    summary: str = Field(default="", max_length=5000)
    summary_evidence: list[Evidence] = Field(default_factory=list, max_length=20)
    employment: list[Employment] = Field(default_factory=list, max_length=100)
    skills: list[Fact] = Field(default_factory=list, max_length=200)
    industries: list[Fact] = Field(default_factory=list, max_length=100)
    qualifications: list[Fact] = Field(default_factory=list, max_length=100)
    languages: list[Fact] = Field(default_factory=list, max_length=100)
    experience_years_override: float | None = Field(default=None, ge=0, le=100, allow_inf_nan=False)


class Criterion(Contract):
    id: UUID
    kind: Literal[
        "capability", "seniority", "employment", "location", "remote", "compensation", "other"
    ]
    description: str = Field(min_length=1, max_length=1000)
    strength: Literal["preferred", "required"] = "preferred"


class Preferences(Contract):
    desired_roles: list[str] = Field(default_factory=list, max_length=30)
    domain_mode: Literal["focus", "expand", "open"] = "open"
    domains: list[str] = Field(default_factory=list, max_length=50)
    criteria: list[Criterion] = Field(default_factory=list, max_length=100)
    excluded_functions: list[str] = Field(default_factory=list, max_length=30)
    goals: str = Field(default="", max_length=3000)
    relevance_threshold: int = Field(default=30, ge=0, le=100)

    @field_validator("desired_roles", "domains", "excluded_functions")
    @classmethod
    def clean_labels(cls, values: list[str]) -> list[str]:
        result: list[str] = []
        for value in values:
            value = value.strip()
            if not value or len(value) > 200:
                raise ValueError("Use non-empty labels of at most 200 characters")
            if value.casefold() not in {item.casefold() for item in result}:
                result.append(value)
        return result

    @model_validator(mode="after")
    def unique_criteria(self) -> "Preferences":
        if len({item.id for item in self.criteria}) != len(self.criteria):
            raise ValueError("Preference IDs must be unique")
        return self


class ProfileInput(Contract):
    facts: Facts
    preferences: Preferences

    def require_reviewed(self) -> None:
        if not self.facts.summary.strip() or not self.preferences.desired_roles:
            raise ValueError("Review the summary and choose at least one desired role")
        if self.preferences.domain_mode != "open" and not self.preferences.domains:
            raise ValueError("Choose domains or select Open to any domain")


def date_bounds(value: str) -> tuple[date, date]:
    if not re.fullmatch(r"\d{4}(-\d{2})?(-\d{2})?", value):
        raise ValueError("Use YYYY, YYYY-MM or YYYY-MM-DD, preserving known precision")
    parts = [int(part) for part in value.split("-")]
    year = parts[0]
    if len(parts) == 1:
        return date(year, 1, 1), date(year, 12, 31)
    month = parts[1]
    if len(parts) == 2:
        return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])
    exact = date(*parts)
    return exact, exact


def union_days(intervals: list[tuple[date, date]]) -> int:
    merged: list[tuple[date, date]] = []
    for start, end in sorted(intervals):
        if end < start:
            continue
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return sum((end - start).days + 1 for start, end in merged)


def experience(facts: Facts, today: date | None = None) -> dict[str, float | str | None]:
    if facts.experience_years_override is not None:
        return {
            "minimum_years": facts.experience_years_override,
            "maximum_years": facts.experience_years_override,
            "basis": "user_override",
        }
    today = today or date.today()
    minimum: list[tuple[date, date]] = []
    maximum: list[tuple[date, date]] = []
    unknown = not facts.employment
    for job in facts.employment:
        if job.origin == "inferred" or job.start is None or (job.end is None and not job.ongoing):
            unknown = True
            continue
        start_min, start_max = date_bounds(job.start)
        end_min, end_max = (today, today) if job.ongoing else date_bounds(job.end or "")
        minimum.append((start_max, min(today, end_min)))
        maximum.append((start_min, min(today, end_max)))
    return {
        "minimum_years": floor(union_days(minimum) / 365.25 * 10) / 10,
        "maximum_years": None if unknown else ceil(union_days(maximum) / 365.25 * 10) / 10,
        "basis": "incomplete_dates" if unknown else "date_union",
    }


def validate_evidence(facts: Facts, spans: list[Span]) -> None:
    available = {span.id: span.text for span in spans}
    references = list(facts.summary_evidence)
    for collection in (facts.skills, facts.industries, facts.qualifications, facts.languages):
        for fact in collection:
            if fact.origin == "extracted" and not fact.evidence:
                raise ValueError("Extracted facts require source evidence")
            references.extend(fact.evidence)
    for role in facts.employment:
        if role.origin == "extracted" and not role.evidence:
            raise ValueError("Extracted roles require source evidence")
        references.extend(role.evidence)
        for fact in role.responsibilities:
            if fact.origin == "extracted" and not fact.evidence:
                raise ValueError("Extracted responsibilities require source evidence")
            references.extend(fact.evidence)
    for reference in references:
        if (
            reference.span_id not in available
            or reference.quote not in available[reference.span_id]
        ):
            raise ValueError("Evidence must quote an existing document span")
