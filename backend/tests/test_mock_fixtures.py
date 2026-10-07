import json

import pytest
from app.ai import matching, provider
from app.ai.contracts import TaskConfig
from app.ai.models import InferenceCall, TaskRevision
from app.config import Settings, get_settings
from app.db import get_engine
from app.domain.matching import category
from app.services.operations import OperationError
from sqlalchemy import select
from sqlalchemy.orm import Session
from synthetic_matching import (
    ALTERNATIVE,
    FACTS,
    MODEL,
    POSTINGS,
    PREFERENCES,
    fixtures,
    write_fixtures,
)


def configure(monkeypatch, tmp_path):
    write_fixtures(tmp_path)
    monkeypatch.setattr(get_settings(), "mock_ai_dir", tmp_path)
    monkeypatch.setattr(
        provider, "client", lambda: pytest.fail("No HTTP is allowed in fixture mode")
    )
    with Session(get_engine()) as db, db.begin():
        row = TaskRevision(
            task="job_matching", revision=1, config=TaskConfig(model=MODEL).model_dump(mode="json")
        )
        db.add(row)
        db.flush()
        return row.id


def test_exact_fixture_cases_validate_without_billing_or_http(monkeypatch, tmp_path):
    identifier = configure(monkeypatch, tmp_path)
    for preferences, expected in [
        (PREFERENCES, ["match", "possible_match", "not_match"]),
        (ALTERNATIVE, ["not_match", "not_match", "match"]),
    ]:
        for posting, verdict in zip(POSTINGS, expected, strict=True):
            result = matching.assess(FACTS, preferences, posting, identifier, None)
            assert category(result, preferences) == verdict
    with Session(get_engine()) as db:
        assert db.scalar(select(InferenceCall)) is None


def test_unknown_input_and_live_mode_do_not_replay_synthetic_results(monkeypatch, tmp_path):
    identifier = configure(monkeypatch, tmp_path)
    with pytest.raises(OperationError) as error:
        matching.assess(
            FACTS.model_copy(update={"summary": "Unrecognised input"}),
            PREFERENCES,
            POSTINGS[0],
            identifier,
            None,
        )
    assert error.value.code == "mock_fixture_missing"
    monkeypatch.setattr(get_settings(), "integration_mode", "live")
    with pytest.raises(OperationError) as error:
        matching.assess(FACTS, PREFERENCES, POSTINGS[0], identifier, None)
    assert error.value.code == "mock_model"
    with pytest.raises(ValueError, match="development-only"):
        Settings(environment="production", mock_ai_dir=tmp_path)


def test_mock_output_requires_real_evidence_validation(monkeypatch, tmp_path):
    identifier = configure(monkeypatch, tmp_path)
    cases = fixtures()
    cases[0]["response"]["function_evidence"][0]["quote"] = "Invented qualification"
    (tmp_path / "job_matching.json").write_text(json.dumps(cases))
    with pytest.raises(OperationError) as error:
        matching.assess(FACTS, PREFERENCES, POSTINGS[0], identifier, None)
    assert error.value.code == "mock_fixture_invalid"
