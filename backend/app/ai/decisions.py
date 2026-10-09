"""OpenRouter Decisions wire protocol: typed questions, typed answers, no free text.

Protocol parsing only; domain interpretation lives in the task adapters. Answers are
normalized fail-closed against the request's own question specification: unknown keys,
missing answers, wrong types, unknown choice values, out-of-range or non-finite numbers,
booleans masquerading as numerics and probability sums outside the documented tolerance
are protocol errors. Bad probabilities are never renormalized. Missing usage cost is
unknown, never zero.
"""

import math
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import Field, TypeAdapter

from app.domain.profile import Contract

# Documented floating-point tolerance for probability sums (choice and score answers).
PROBABILITY_TOLERANCE = Decimal("0.02")


class DecisionsQuestion(Contract):
    type: Literal["choice", "noul", "score"]
    instructions: str = Field(min_length=1)
    # choice: {label: rubric}; noul: {"true": rubric, "false": rubric}; score: [lowest..highest]
    criteria: dict[str, str] | list[str] | None = None


class ChoiceAnswer(Contract):
    type: Literal["choice"] = "choice"
    choice: str = Field(min_length=1, max_length=200)
    confidence: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    probabilities: dict[str, float] | None = None


class NoulAnswer(Contract):
    type: Literal["noul"] = "noul"
    noul: float = Field(ge=0, le=1, allow_inf_nan=False)


class ScoreAnswer(Contract):
    type: Literal["score"] = "score"
    score: float = Field(allow_inf_nan=False)
    confidence: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    probabilities: dict[str, float] | None = None
    legend: dict[str, Any] | None = None


Answer: TypeAdapter[ChoiceAnswer | NoulAnswer | ScoreAnswer] = TypeAdapter(
    Annotated[ChoiceAnswer | NoulAnswer | ScoreAnswer, Field(discriminator="type")]
)


class DecisionsUsage(Contract):
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    # Documented optional: a missing cost is unknown billing, never zero.
    cost: float | None = Field(default=None, ge=0, allow_inf_nan=False)


class DecisionsResponse(Contract):
    model: str = Field(min_length=1, max_length=200)
    answers: dict[str, ChoiceAnswer | NoulAnswer | ScoreAnswer]
    usage: DecisionsUsage
    id: str | None = Field(default=None, max_length=200)
    provider: str | None = Field(default=None, max_length=200)


def _finite_number(value: object, field: str) -> None:
    """Booleans and non-finite values must fail before pydantic coerces bool to float."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{field} must be a finite number, not {type(value).__name__}")


def parse_response(data: object) -> DecisionsResponse:
    """Parse and type-check a Decisions response envelope."""
    if not isinstance(data, dict):
        raise ValueError("Decisions response must be a JSON object")
    raw_answers = data.get("answers")
    if not isinstance(raw_answers, dict):
        raise ValueError("Decisions response answers must be an object")
    for key, raw in raw_answers.items():
        if not isinstance(raw, dict):
            raise ValueError(f"answer {key!r} must be an object")
        for field in ("noul", "score", "confidence"):
            if field in raw:
                _finite_number(raw[field], f"answer {key!r} {field}")
        probabilities = raw.get("probabilities")
        if probabilities is not None:
            if not isinstance(probabilities, dict):
                raise ValueError(f"answer {key!r} probabilities must be an object")
            for label, value in probabilities.items():
                _finite_number(value, f"answer {key!r} probability {label!r}")
    usage = data.get("usage")
    if isinstance(usage, dict) and usage.get("cost") is not None:
        _finite_number(usage["cost"], "usage cost")
    return DecisionsResponse.model_validate(
        {
            **data,
            "answers": {key: Answer.validate_python(value) for key, value in raw_answers.items()},
        }
    )


def _probabilities(probabilities: dict[str, float] | None, keys: set[str], what: str) -> None:
    if probabilities is None:
        return  # Optional metadata: absence is tolerated, wrong contents are not.
    if set(probabilities) != keys:
        raise ValueError(f"{what} probabilities do not match the allowed keys")
    total = Decimal(0)
    for label, value in probabilities.items():
        if isinstance(value, bool) or not Decimal(str(value)).is_finite():
            raise ValueError(f"{what} probability for {label!r} is not a finite number")
        if not 0 <= value <= 1:
            raise ValueError(f"{what} probability for {label!r} is out of range")
        total += Decimal(str(value))
    if abs(total - 1) > PROBABILITY_TOLERANCE:
        raise ValueError(f"{what} probability sum is outside the documented tolerance")


def normalize(
    questions: dict[str, DecisionsQuestion], response: DecisionsResponse
) -> dict[str, ChoiceAnswer | NoulAnswer | ScoreAnswer]:
    """Fail-closed normalization against the request's question specification."""
    unexpected = set(response.answers) - set(questions)
    if unexpected:
        raise ValueError(f"answers for unknown questions: {sorted(unexpected)}")
    missing = set(questions) - set(response.answers)
    if missing:
        raise ValueError(f"missing answers for questions: {sorted(missing)}")
    for key, question in questions.items():
        answer = response.answers[key]
        if answer.type != question.type:
            raise ValueError(f"answer {key!r} has type {answer.type!r}, expected {question.type!r}")
        if question.type == "choice":
            assert isinstance(answer, ChoiceAnswer)
            labels = set(question.criteria or {})
            if answer.choice not in labels:
                raise ValueError(f"answer {key!r} selected unknown choice {answer.choice!r}")
            _probabilities(answer.probabilities, labels, f"answer {key!r}")
        elif question.type == "score":
            assert isinstance(answer, ScoreAnswer)
            levels = len(question.criteria or [])
            if not 0 <= answer.score <= levels - 1:
                raise ValueError(f"answer {key!r} score is outside the criterion range")
            _probabilities(
                answer.probabilities, {str(index) for index in range(levels)}, f"answer {key!r}"
            )
    return response.answers


def request_body(
    model: str, state: Any, questions: dict[str, DecisionsQuestion], provider: dict[str, Any]
) -> dict[str, Any]:
    """Build the Decisions request. Only documented Decisions fields are sent."""
    return {
        "model": model,
        "state": state,
        "questions": {
            key: question.model_dump(mode="json", exclude_none=True)
            for key, question in questions.items()
        },
        "provider": provider,
    }


@dataclass
class DecisionsTask:
    """Task-boundary adapter input: the protocol payload plus the domain interpreter."""

    state: Any
    questions: dict[str, DecisionsQuestion]
    interpret: Callable[[dict[str, ChoiceAnswer | NoulAnswer | ScoreAnswer]], Any]
