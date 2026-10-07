"""Broad shortlist policy. Scores are coarse relevance aids, never probabilities."""

from typing import Literal
from uuid import UUID

from app.domain.profile import Contract, Evidence, Preferences, Span
from pydantic import Field

POLICY_VERSION = "broad-v1"
Category = Literal["match", "possible_match", "not_match"]


class Reason(Contract):
    text: str = Field(min_length=1, max_length=1000)
    evidence: list[Evidence] = Field(min_length=1, max_length=20)


class CriterionResult(Contract):
    preference_id: UUID
    status: Literal["met", "not_met", "unknown"]
    explanation: str = Field(min_length=1, max_length=1000)
    evidence: list[Evidence] = Field(default_factory=list, max_length=20)
    # In particular, salary currencies/periods and remote/work-authorisation are not
    # interchangeable. A conflict without comparable evidence stays unknown.
    comparable: bool = False


class Assessment(Contract):
    primary_function: str = Field(min_length=1, max_length=300)
    relation: Literal["aligned", "adjacent", "unrelated", "unclear"]
    function_evidence: list[Evidence] = Field(min_length=1, max_length=20)
    relevance_score: int | None = Field(default=None, ge=0, le=100, strict=True)
    score_evidence: list[Evidence] = Field(default_factory=list, max_length=20)
    plausible_connection: bool
    connection_evidence: list[Evidence] = Field(default_factory=list, max_length=20)
    criteria: list[CriterionResult] = Field(default_factory=list, max_length=100)
    domain_status: Literal["met", "not_met", "unknown"]
    domain_evidence: list[Evidence] = Field(default_factory=list, max_length=20)
    important_unknowns: bool
    transferable: list[Reason] = Field(default_factory=list, max_length=10)
    reasons: list[Reason] = Field(default_factory=list, max_length=3)
    gaps: list[Reason] = Field(default_factory=list, max_length=3)


def has_source(evidence: list[Evidence], prefix: str) -> bool:
    return any(item.span_id.startswith(prefix + ":") for item in evidence)


def validate(assessment: Assessment, preferences: Preferences, spans: list[Span]) -> None:
    lookup = {span.id: span.text for span in spans}
    if len(lookup) != len(spans):
        raise ValueError("Assessment evidence spans need unique IDs.")
    references = [
        *assessment.function_evidence,
        *assessment.score_evidence,
        *assessment.connection_evidence,
        *assessment.domain_evidence,
    ]
    for reason in [*assessment.transferable, *assessment.reasons, *assessment.gaps]:
        references.extend(reason.evidence)
    criteria = {criterion.id: criterion for criterion in preferences.criteria}
    if len({result.preference_id for result in assessment.criteria}) != len(
        assessment.criteria
    ) or {result.preference_id for result in assessment.criteria} != set(criteria):
        raise ValueError("Every saved preference must be assessed exactly once.")
    for result in assessment.criteria:
        references.extend(result.evidence)
        if result.status != "unknown" and (
            not result.comparable
            or not has_source(result.evidence, "job")
            or not any(
                item.span_id == f"preference:{result.preference_id}" for item in result.evidence
            )
        ):
            raise ValueError(
                "Known preference outcomes need comparable listing/preference evidence."
            )
    if any(
        item.span_id not in lookup or item.quote not in lookup[item.span_id] for item in references
    ):
        raise ValueError(
            "Assessment evidence must quote supplied profile, preference or job spans."
        )
    if not any(item.span_id == "job:description" for item in assessment.function_evidence):
        raise ValueError("Primary function needs cited job duties.")
    if assessment.relation != "unclear" and not any(
        item.span_id in {"preference:desired_roles", "preference:excluded_functions"}
        for item in assessment.function_evidence
    ):
        raise ValueError("Function relation needs the owner's desired or excluded functions.")
    if assessment.relevance_score is not None and (
        not has_source(assessment.score_evidence, "job")
        or not (
            has_source(assessment.score_evidence, "profile")
            or has_source(assessment.score_evidence, "preference")
        )
    ):
        raise ValueError("A relevance score needs job and candidate-intent evidence.")
    if assessment.plausible_connection and (
        not has_source(assessment.connection_evidence, "job")
        or not (
            has_source(assessment.connection_evidence, "profile")
            or has_source(assessment.connection_evidence, "preference")
        )
    ):
        raise ValueError("A plausible connection needs evidence from both sides.")
    if (
        preferences.domain_mode == "focus"
        and assessment.domain_status != "unknown"
        and (
            not has_source(assessment.domain_evidence, "job")
            or not any(item.span_id == "preference:domains" for item in assessment.domain_evidence)
        )
    ):
        raise ValueError("Known focus-domain outcomes need domain and listing evidence.")


def category(assessment: Assessment, preferences: Preferences) -> Category:
    """Call only after evidence validation; deterministic priority comes from MATCHING.md."""
    if assessment.relation == "unrelated":
        return "not_match"
    required = {
        criterion.id for criterion in preferences.criteria if criterion.strength == "required"
    }
    if any(
        result.preference_id in required and result.status == "not_met"
        for result in assessment.criteria
    ):
        return "not_match"
    if preferences.domain_mode == "focus" and assessment.domain_status == "not_met":
        return "not_match"
    unknown = (
        assessment.important_unknowns
        or any(
            result.preference_id in required and result.status == "unknown"
            for result in assessment.criteria
        )
        or (preferences.domain_mode == "focus" and assessment.domain_status == "unknown")
    )
    score = assessment.relevance_score
    if (
        assessment.relation in {"aligned", "adjacent"}
        and score is not None
        and score >= preferences.relevance_threshold
    ):
        return "match" if score >= 60 and not unknown else "possible_match"
    if assessment.plausible_connection and (assessment.relation == "unclear" or score is None):
        return "possible_match"
    if score is not None and score < preferences.relevance_threshold:
        return "not_match"
    # Unsupported/insufficient output is a visible assessment error, never a rejection.
    raise ValueError("Insufficient evidence to derive a matching category.")
