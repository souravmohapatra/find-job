from decimal import Decimal

import pytest
from app.ai.run_ledger import TOTAL_REQUESTS, BudgetRefused, RunLedger


def test_request_limit_refuses_before_any_admission(tmp_path):
    ledger = RunLedger(tmp_path / "ledger.json")
    for index in range(TOTAL_REQUESTS):
        ledger.admit(f"call-{index}", Decimal("0.001"))
        ledger.settle(f"call-{index}", Decimal("0"))
    with pytest.raises(BudgetRefused) as refused:
        ledger.admit("one-too-many", Decimal("0.001"))
    assert refused.value.reason == "request_limit"
    assert ledger.summary()["attempts"] == TOTAL_REQUESTS


def test_spend_limit_counts_held_reservations_not_only_known_cost(tmp_path):
    ledger = RunLedger(tmp_path / "ledger.json")
    ledger.admit("first", Decimal("0.60"))
    # The first call is still in flight: its bound is held, so a second bound must not fit.
    with pytest.raises(BudgetRefused) as refused:
        ledger.admit("second", Decimal("0.50"))
    assert refused.value.reason == "spend_limit"


def test_unknown_cost_stays_held_and_survives_restart(tmp_path):
    path = tmp_path / "ledger.json"
    RunLedger(path).admit("ambiguous", Decimal("0.40"))
    RunLedger(path).settle("ambiguous", None)

    restarted = RunLedger(path).summary()
    assert restarted["unresolved_calls"] == ["ambiguous"]
    assert restarted["held_usd"] == "0.40"
    with pytest.raises(BudgetRefused):
        RunLedger(path).admit("after-restart", Decimal("0.61"))


def test_known_cost_releases_hold_into_known_spend(tmp_path):
    ledger = RunLedger(tmp_path / "ledger.json")
    ledger.admit("settled", Decimal("0.40"))
    ledger.settle("settled", Decimal("0.05"))
    summary = ledger.summary()
    assert summary["known_usd"] == "0.05"
    assert summary["held_usd"] == "0"
    assert summary["unresolved_calls"] == []


def test_non_finite_or_negative_costs_are_rejected(tmp_path):
    ledger = RunLedger(tmp_path / "ledger.json")
    ledger.admit("bad", Decimal("0.10"))
    with pytest.raises(ValueError):
        ledger.settle("bad", Decimal("-0.01"))
    with pytest.raises(ValueError):
        ledger.settle("bad", Decimal("NaN"))
    # Still held: an invalid settlement never releases the bound.
    assert ledger.summary()["unresolved_calls"] == ["bad"]
