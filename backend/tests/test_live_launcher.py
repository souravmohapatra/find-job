"""Offline tests for the Phase A launcher's provider-backstop gate: no live GETs."""

import importlib.util
import math
from pathlib import Path
from typing import Any

import httpx
import pytest

ROOT = Path(__file__).parents[2]


def load_launcher() -> Any:
    path = ROOT / "scripts" / "validate-live-api.py"
    spec = importlib.util.spec_from_file_location("validate_live_api", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def key_metadata(data: dict[str, Any]) -> httpx.Response:
    # Raw content, not json=: non-compliant NaN must reach the parser as it would
    # on the wire, where a non-strict server can emit it.
    import json

    return httpx.Response(200, content=json.dumps({"data": data}).encode())


@pytest.fixture
def launcher(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, tmp_path_factory: Any
) -> Any:
    module = load_launcher()
    key = tmp_path / "key"
    key.write_text("synthetic-key-never-printed")
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "openrouter_key_file", key)
    # Metadata GETs are faked; nothing leaves the machine.
    monkeypatch.setattr(module, "METADATA_URL", "https://openrouter.invalid/auth/key")
    return module


def metadata_get(
    monkeypatch: pytest.MonkeyPatch, data: dict[str, Any], calls: list[str]
) -> None:
    def fake_get(url: str, **kwargs: Any) -> httpx.Response:
        calls.append(url)
        return key_metadata(data)

    monkeypatch.setattr(httpx, "get", fake_get)


def test_valid_static_limit_within_ceiling_passes(launcher: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    metadata_get(monkeypatch, {"usage": 0, "limit": 1, "limit_remaining": 1, "limit_reset": None}, calls)
    state: dict[str, int] = {"attempts": 0}
    launcher.check_spending_backstop(state)
    assert state["attempts"] == 1 and len(calls) == 1
    assert calls[0] == launcher.METADATA_URL


@pytest.mark.parametrize(
    "data",
    [
        {"usage": 0, "limit": 5},  # oversized ceiling
        {"usage": 0, "limit": None},  # unset backstop
        {"usage": 0, "limit": float("nan")},  # non-finite limit slips naive checks
        {"usage": float("nan"), "limit": 1},  # non-finite usage
        {"usage": 0, "limit": 1, "limit_reset": "monthly"},  # resetting allowance
        {"usage": 1, "limit": 1, "limit_remaining": 0},  # exhausted
        {"usage": 0, "limit": 1, "limit_remaining": float("nan")},  # unusable remaining
    ],
)
def test_unenforceable_backstops_are_rejected(
    launcher: Any, monkeypatch: pytest.MonkeyPatch, data: dict[str, Any]
) -> None:
    metadata_get(monkeypatch, data, [])
    with pytest.raises(SystemExit):
        launcher.check_spending_backstop({"attempts": 0})


def test_backstop_still_counts_metadata_attempt_on_failure(
    launcher: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    metadata_get(monkeypatch, {"usage": 0, "limit": None}, [])
    state: dict[str, int] = {"attempts": 0}
    with pytest.raises(SystemExit):
        launcher.check_spending_backstop(state)
    assert state["attempts"] == 1
