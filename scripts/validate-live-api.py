"""Development-only Phase A launcher for bounded live OpenRouter validation.

Default behavior is offline: verify the isolation preconditions, reconcile the
persistent run ledger, demonstrate the budget refusals (Gate A) and provision a
dedicated disposable database. No external request is made.

--execute-live additionally provisions this run's temporary owner-only key bridge
under the ignored .secrets/ directory, verifies key availability through the
application's own settings path and checks the key's spending backstop with one
authenticated metadata GET. Billable probes belong to the later phases and are not
implemented in this launcher yet.

The script never prints the key, the database URL or other secret material, never
executes shell text from .env, and removes only this run's temporary secret on
orderly shutdown.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from decimal import Decimal
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / ".data"
SECRETS_DIR = ROOT / ".secrets"

METADATA_URL = "https://openrouter.ai/api/v1/auth/key"


def fail(message: str) -> "SystemExit":
    print(f"BLOCKED: {message}", file=sys.stderr)
    return SystemExit(2)


def read_env_key(path: Path) -> str:
    """Read the selected key from .env with a line parser; never interpolate or execute."""
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if stripped.startswith("OPENROUTER_KEY="):
            value = stripped.split("=", 1)[1].strip().strip("'\"")
            if value:
                return value
    return ""


def ensure_ignored(relative: str) -> None:
    # Directory-only .gitignore patterns need the trailing slash when the path is new.
    # --quiet accepts a single pathname, so probe the forms one at a time.
    probes = [relative] if relative.endswith("/") else [f"{relative}/", relative]
    for probe in probes:
        result = subprocess.run(["git", "check-ignore", "-q", "--", probe], cwd=ROOT, check=False)
        if result.returncode == 0:
            return
    raise fail(f"{relative} is not ignored by git; refusing to continue")


def verify_test_database_listener() -> None:
    """Require the published listener to be loopback-only before any connection."""
    listing = subprocess.run(["ss", "-ltn"], capture_output=True, text=True, check=True).stdout
    bound = [line for line in listing.splitlines() if ":55439" in line]
    if not bound:
        raise fail("no listener on 127.0.0.1:55439; start compose.test.yaml first")
    # Columns: State Recv-Q Send-Q LocalAddr:Port PeerAddr:Port; local is [-2].
    if any(not line.split()[-2].startswith("127.0.0.1") for line in bound):
        raise fail("port 55439 is published beyond loopback; refusing to continue")


def provision_database(run_id: str) -> None:
    """Create this run's disposable database in the isolated test container."""
    if not re.fullmatch(r"[a-z0-9_]+", run_id):
        raise fail("run id must be lowercase alphanumeric/underscore")
    name = f"jobfinder_test_live_api_{run_id}"
    subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            "compose.test.yaml",
            "exec",
            "-T",
            "db",
            "psql",
            "-U",
            "jobfinder",
            "-d",
            "jobfinder_test",
            "-v",
            "ON_ERROR_STOP=1",
            "-c",
            f'CREATE DATABASE "{name}"',
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )  # Existing databases from an interrupted run are reused as-is.
    print(f"database ready: {name} (name only; URL never printed)")


def initialize_schema_and_owner(limits_calls: int, limits_usd: Decimal) -> None:
    from alembic import command
    from alembic.config import Config

    from app.ai.contracts import AiLimits
    from app.ai.models import AiLimitsRow
    from app.cli import create_owner
    from app.db import get_engine
    from app.tasks.worker import bootstrap_queue

    config = Config(str(ROOT / "backend/alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "backend/migrations"))
    command.upgrade(config, "head")
    bootstrap_queue()
    # Synthetic owner for a disposable local database; mirrors the test-suite convention.
    # An interrupted run may have created it already; same database, same owner.
    try:
        create_owner("owner", "synthetic-live-owner-password")
    except ValueError as error:
        if "already exists" not in str(error):
            raise
    capped = AiLimits(daily_calls=limits_calls, daily_usd=limits_usd)
    from sqlalchemy.orm import Session

    with Session(get_engine()) as db, db.begin():
        row = db.get(AiLimitsRow, 1)
        if row is None:
            db.add(AiLimitsRow(id=1, revision=0, settings=capped.model_dump(mode="json")))
        else:
            row.settings = capped.model_dump(mode="json")
    print(f"schema initialized; app daily limits capped at {limits_calls} calls / ${limits_usd}")


def demonstrate_offline_refusals(run_id: str) -> None:
    """Gate A: prove both caps refuse before any I/O and survive a restart."""
    from app.ai.run_ledger import TOTAL_REQUESTS, BudgetRefused, RunLedger

    # Fresh per-run ledgers: a pre-filled demonstration ledger from an earlier run
    # would refuse its own prefill. Nothing here is real spend; remove it afterwards.
    folder = DATA_DIR / f"gate_a_{run_id}"
    request_ledger = RunLedger(folder / "request-cap.json")
    for index in range(TOTAL_REQUESTS):
        request_ledger.admit(f"prefill-{index}", Decimal("0.001"))
        request_ledger.settle(f"prefill-{index}", Decimal(0))
    try:
        RunLedger(folder / "request-cap.json").admit("one-too-many", Decimal("0.001"))
        raise fail("request-limit refusal did not trigger")
    except BudgetRefused as refused:
        assert refused.reason == "request_limit"

    spend_ledger_path = folder / "spend-cap.json"
    RunLedger(spend_ledger_path).admit("in-flight", Decimal("0.90"))
    try:
        RunLedger(spend_ledger_path).admit("next", Decimal("0.11"))
        raise fail("spend-limit refusal did not trigger")
    except BudgetRefused as refused:
        assert refused.reason == "spend_limit"

    # A fresh instance must still refuse: allowance lives outside any database or process.
    try:
        RunLedger(spend_ledger_path).admit("after-restart", Decimal("0.11"))
        raise fail("ledger did not persist the refusal across restart")
    except BudgetRefused:
        pass
    print(
        "Gate A refusals demonstrated offline: request cap, in-flight spend cap,"
        " and persistence across restart."
    )
    import shutil

    shutil.rmtree(folder)


def build_key_bridge(run_id: str) -> tuple[Path, str]:
    """Create this run's owner-only key-only file from .env; return (bridge path, run dir)."""
    key = read_env_key(ROOT / ".env")
    if not key:
        raise fail("OPENROUTER_KEY is absent or empty in .env")
    run_dir = SECRETS_DIR / f"live-api-{run_id}"
    try:
        run_dir.mkdir(mode=0o700)
    except FileExistsError as error:
        raise fail(
            f"bridge directory {run_dir} already exists; remove it before rerunning"
        ) from error
    bridge = run_dir / "openrouter_api_key"
    try:
        descriptor = os.open(bridge, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as error:
        raise fail(f"bridge file {bridge} already exists") from error
    with os.fdopen(descriptor, "w") as stream:
        stream.write(key)
    return bridge, run_dir


def remove_key_bridge(run_dir: Path) -> None:
    """Remove only this run's temporary secret on orderly shutdown."""
    bridge = run_dir / "openrouter_api_key"
    try:
        bridge.unlink(missing_ok=True)
        run_dir.rmdir()
    except OSError as error:
        print(f"WARNING: temporary key bridge removal failed: {error}", file=sys.stderr)


def check_spending_backstop(metadata_state: dict[str, int]) -> None:
    """One authenticated metadata GET; prints coarse limits only, never key material."""
    import httpx

    from app.config import get_settings

    key = get_settings().openrouter_key_file.read_text().strip()
    response = httpx.get(
        METADATA_URL,
        headers={"Authorization": f"Bearer {key}"},
        timeout=30,
        follow_redirects=False,
    )
    metadata_state["attempts"] += 1
    if response.status_code != 200:
        raise fail(f"key metadata check returned HTTP {response.status_code}; diagnose offline")
    data = response.json().get("data", {})
    usage = data.get("usage")
    limit = data.get("limit")
    print(f"key backstop: usage={usage} limit={limit if limit is not None else 'unset'}")


def save_run_metadata(path: Path, metadata: dict[str, object]) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        json.dump(metadata, stream, indent=2, sort_keys=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute-live", action="store_true", help="enable live-mode preparation")
    parser.add_argument("--run-id", default=time.strftime("%Y%m%d_%H%M%S"))
    args = parser.parse_args()
    run_id = args.run_id

    ensure_ignored(".env")
    ensure_ignored(".data")
    ensure_ignored(".secrets")

    # Process configuration precedes every application import (Phase A step 5).
    os.environ["JOBFINDER_ENVIRONMENT"] = "development"
    os.environ["JOBFINDER_INTEGRATION_MODE"] = "live"
    os.environ["JOBFINDER_SEARCH_MODE"] = "mock"
    os.environ["JOBFINDER_NOTIFICATION_MODE"] = "mock"
    os.environ.pop("JOBFINDER_MOCK_AI_DIR", None)
    os.environ.pop("JOBFINDER_FETCHER_URL", None)
    os.environ.pop("JOBFINDER_MOCK_SEARCH_DIR", None)
    DATA_DIR.mkdir(mode=0o700, exist_ok=True)
    os.environ["JOBFINDER_LIVE_LEDGER_PATH"] = str(DATA_DIR / "live_run_ledger.json")
    os.environ["JOBFINDER_DOCUMENT_DIR"] = str(DATA_DIR / f"live_run_{run_id}" / "documents")

    sys.path.insert(0, str(ROOT / "backend"))

    bridge_dir: Path | None = None
    metadata_state = {"attempts": 0}
    try:
        key = read_env_key(ROOT / ".env")
        if not key:
            raise fail("OPENROUTER_KEY is absent or empty in .env")
        print(f"key present in .env ({len(key)} characters; value never printed)")

        # The settings singleton caches paths at first use: the bridge must exist and
        # its path must be set before the first application import, not after.
        if args.execute_live:
            bridge, bridge_dir = build_key_bridge(run_id)
            os.environ["JOBFINDER_OPENROUTER_KEY_FILE"] = str(bridge)

        from app.ai.run_ledger import RunLedger

        ledger = RunLedger(Path(os.environ["JOBFINDER_LIVE_LEDGER_PATH"]))
        summary = ledger.summary()
        remaining_requests = 60 - int(summary["attempts"])
        remaining_usd = Decimal(summary["spend_remaining_usd"])
        print(
            f"run ledger: attempts={summary['attempts']} known=${summary['known_usd']}"
            f" held=${summary['held_usd']} remaining=${summary['spend_remaining_usd']}"
            f" unresolved={len(summary['unresolved_calls'])}"
        )
        if summary["unresolved_calls"]:
            raise fail("unresolved held costs remain; reconcile before further dispatch")
        if remaining_requests <= 0 or remaining_usd <= 0:
            raise fail("the cumulative validation allowance is exhausted")

        demonstrate_offline_refusals(run_id)

        verify_test_database_listener()
        provision_database(run_id)

        from app.config import get_settings

        password = (SECRETS_DIR / "test_db_password").read_text().strip()
        os.environ["JOBFINDER_DATABASE_URL"] = (
            f"postgresql+psycopg://jobfinder:{quote(password, safe='')}"
            f"@127.0.0.1:55439/jobfinder_test_live_api_{run_id}"
        )
        # App daily limits never exceed the remaining cumulative allowance (Phase A step 9).
        initialize_schema_and_owner(min(remaining_requests, 60), min(remaining_usd, Decimal("1")))

        settings = get_settings()
        observed = {
            "environment": settings.environment,
            "integration_mode": settings.integration_mode,
            "search_mode": settings.search_mode,
            "notification_mode": settings.notification_mode,
            "mock_ai_dir": settings.mock_ai_dir,
            "fetcher_url": settings.fetcher_url,
        }
        assert observed == {
            "environment": "development",
            "integration_mode": "live",
            "search_mode": "mock",
            "notification_mode": "mock",
            "mock_ai_dir": None,
            "fetcher_url": None,
        }, observed
        print(f"process settings verified: {observed}")
        print("concurrency for live validation: one (launcher is single-threaded)")

        run_metadata = {
            "run_id": run_id,
            "database": f"jobfinder_test_live_api_{run_id}",
            "ledger": os.environ["JOBFINDER_LIVE_LEDGER_PATH"],
            "documents": os.environ["JOBFINDER_DOCUMENT_DIR"],
            "metadata_attempts": metadata_state["attempts"],
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        }

        if args.execute_live:
            # Availability through the application's own settings path, value never printed.
            from app.ai.provider import key_available

            if not key_available():
                raise fail("the application could not read the temporary key bridge")
            print("key bridge verified through the application settings path")
            check_spending_backstop(metadata_state)
            run_metadata["bridge"] = str(bridge_dir)
            run_metadata["metadata_attempts"] = metadata_state["attempts"]
        save_run_metadata(DATA_DIR / f"live_run_{run_id}.json", run_metadata)
        print(f"run metadata saved: .data/live_run_{run_id}.json (no secrets)")

        if not args.execute_live:
            print(
                "Phase A offline preparation complete. Billable probes require Phase B"
                " mocked-transport coverage first; rerun with --execute-live only for"
                " key-bridge preparation and the metadata backstop check."
            )
        else:
            print(
                "Phase A live preparation complete. Billable probes are not implemented"
                " in this launcher batch yet; the bridge is removed on shutdown."
            )
        return 0
    finally:
        if bridge_dir is not None:
            remove_key_bridge(bridge_dir)
            print("temporary key bridge removed (this run's secret only)")


if __name__ == "__main__":
    raise SystemExit(main())
