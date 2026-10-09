"""Explicit synthetic responses for development; unknown input never gets a guessed result."""

import json
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel

from app.ai.contracts import TaskKey
from app.config import get_settings
from app.services.operations import OperationError


def replay[T: BaseModel](
    task: TaskKey,
    model: str,
    system: str,
    payload: object,
    output: type[T],
    validate: Callable[[T], None] | None,
    prompt_version: str,
    schema_version: str,
) -> T:
    settings = get_settings()
    if settings.integration_mode != "mock" or settings.environment == "production":
        raise OperationError("mock_fixture_forbidden", "Synthetic AI fixtures are disabled here.")
    if settings.mock_ai_dir is None:
        raise OperationError(
            "mock_fixture_missing", "No synthetic AI fixture directory is configured.", blocked=True
        )
    try:
        with (settings.mock_ai_dir / f"{task}.json").open("rb") as stream:
            raw = stream.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise ValueError
        cases: Any = json.loads(raw)
        if not isinstance(cases, list) or len(cases) > 50:
            raise ValueError
        matches = [
            case
            for case in cases
            if isinstance(case, dict)
            and (
                case.get("model") == model
                and case.get("system") == system
                and case.get("input") == payload
                and case.get("prompt_version") == prompt_version
                and case.get("schema_version") == schema_version
            )
        ]
        if not matches:
            raise OperationError(
                "mock_fixture_missing",
                "This input has no synthetic AI response. Use a documented development example "
                "or configure live inference later.",
                blocked=True,
            )
        if len(matches) != 1:
            raise ValueError
        result = output.model_validate(matches[0]["response"])
        if validate:
            validate(result)
        return result
    except OperationError:
        raise
    except (OSError, ValueError, TypeError, KeyError) as from_error:
        raise OperationError(
            "mock_fixture_invalid",
            "The synthetic AI fixture is unavailable or invalid.",
            blocked=True,
        ) from from_error
