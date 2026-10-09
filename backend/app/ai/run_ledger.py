"""Persistent cumulative admission ledger for bounded live API validation.

Development-only. It survives process restarts, daily resets and test-database recreation.
Every outbound inference POST is admitted here before dispatch; unresolved cost stays held.
"""

import fcntl
import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path
from typing import Any

TOTAL_USD = Decimal("1")
TOTAL_REQUESTS = 60


class BudgetRefused(RuntimeError):
    """Raised before network I/O when the cumulative request or spend limit would be exceeded."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class RunLedger:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.lock_path = path.with_name(path.name + ".lock")

    @contextmanager
    def _locked(self) -> Iterator[None]:
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with self.lock_path.open("a+") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    def _read(self) -> dict[str, Any]:
        if not self.path.exists():
            if self.path.with_name(self.path.name + ".initialized").exists():
                # The marker persists after first initialization: a missing ledger
                # beside it is lost accounting, not a fresh allowance. Fail closed.
                raise RuntimeError(
                    f"The run ledger file {self.path} disappeared after initialization;"
                    " reconcile the true request and spend state before further dispatch."
                )
            initial_state: dict[str, Any] = {"attempts": 0, "known_usd": "0", "held": {}}
            self._write(initial_state)
            self._write_marker()
            return initial_state
        state: dict[str, Any] = json.loads(self.path.read_text())
        return state

    def _write_marker(self) -> None:
        marker = self.path.with_name(self.path.name + ".initialized")
        descriptor = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w") as handle:
            handle.write("initialized\n")
            handle.flush()
            os.fsync(handle.fileno())

    def _write(self, state: dict[str, Any]) -> None:
        temporary = self.path.with_name(self.path.name + ".tmp")
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w") as handle:
            handle.write(json.dumps(state, sort_keys=True))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, self.path)
        # Durability for the hard cap: the rename itself must survive a host crash.
        directory = os.open(self.path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)

    def remaining_usd(self) -> Decimal:
        """Spend that admitted calls have not yet reserved or reported."""
        with self._locked():
            state = self._read()
            held = sum((Decimal(value) for value in state["held"].values()), Decimal(0))
            return TOTAL_USD - Decimal(state["known_usd"]) - held

    def admit(self, call_id: str, reserve_usd: Decimal) -> None:
        """Count one outbound attempt and hold its bound, or refuse before any I/O."""
        if not reserve_usd.is_finite() or reserve_usd <= 0:
            raise ValueError("reservation must be finite and positive")
        with self._locked():
            state = self._read()
            if call_id in state["held"]:
                raise ValueError("call id already admitted")
            held = sum((Decimal(value) for value in state["held"].values()), Decimal(0))
            if state["attempts"] + 1 > TOTAL_REQUESTS:
                raise BudgetRefused("request_limit")
            if Decimal(state["known_usd"]) + held + reserve_usd > TOTAL_USD:
                raise BudgetRefused("spend_limit")
            state["attempts"] += 1
            state["held"][call_id] = str(reserve_usd)
            self._write(state)

    def settle(self, call_id: str, actual_usd: Decimal | None) -> None:
        """Release a hold into known spend. An unknown cost (None) stays held.

        Idempotent: the application can record the same finished call more than once
        (for example "completed" then "succeeded" from one response). A settle for a
        call that is no longer held is a no-op.
        """
        with self._locked():
            state = self._read()
            if call_id not in state["held"]:
                return
            if actual_usd is None:
                return
            if not actual_usd.is_finite() or actual_usd < 0:
                raise ValueError("actual cost must be finite and non-negative")
            state["known_usd"] = str(Decimal(state["known_usd"]) + actual_usd)
            del state["held"][call_id]
            self._write(state)

    def summary(self) -> dict[str, Any]:
        with self._locked():
            state = self._read()
        held = sum((Decimal(value) for value in state["held"].values()), Decimal(0))
        return {
            "attempts": state["attempts"],
            "attempts_remaining": TOTAL_REQUESTS - state["attempts"],
            "known_usd": state["known_usd"],
            "held_usd": str(held),
            "unresolved_calls": sorted(state["held"]),
            "spend_remaining_usd": str(TOTAL_USD - Decimal(state["known_usd"]) - held),
        }
