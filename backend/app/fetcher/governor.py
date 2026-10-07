"""Small persistent origin ledger, shared by all requests in the isolated fetcher."""

import sqlite3
import time
from pathlib import Path

from app.fetcher.contracts import FetchFailure


def connection(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    db = sqlite3.connect(path, timeout=1, isolation_level=None)
    path.chmod(0o600)
    db.execute(
        "CREATE TABLE IF NOT EXISTS origins (origin TEXT PRIMARY KEY, "
        "next_at REAL NOT NULL, cooldown REAL NOT NULL, last_start REAL NOT NULL)"
    )
    return db


def reserve(path: Path, origin: str, spacing: float = 2) -> float:
    db = connection(path)
    try:
        db.execute("BEGIN IMMEDIATE")
        clock = time.time()
        row = db.execute(
            "SELECT next_at, cooldown, last_start FROM origins WHERE origin=?", (origin,)
        ).fetchone()
        if row and row[1] > clock:
            raise FetchFailure("source_cooldown", retry_after=max(1, int(row[1] - clock) + 1))
        db.execute("DELETE FROM origins WHERE next_at < ? AND cooldown < ?", (clock - 86400, clock))
        if row is None and db.execute("SELECT count(*) FROM origins").fetchone()[0] >= 4096:
            raise FetchFailure("origin_budget", retry_after=3600)
        start = max(clock, row[0] if row else clock, row[2] + spacing if row else clock)
        if start - clock > 25:
            raise FetchFailure("source_cooldown", retry_after=int(start - clock) + 1)
        db.execute(
            "INSERT INTO origins VALUES (?, ?, 0, ?) ON CONFLICT(origin) DO UPDATE SET "
            "next_at=excluded.next_at, last_start=excluded.last_start",
            (origin, start + spacing, start),
        )
        db.commit()
        return max(0, start - clock)
    finally:
        db.close()


def cooldown(path: Path, origin: str, seconds: int) -> None:
    db = connection(path)
    try:
        clock = time.time()
        db.execute(
            "INSERT INTO origins VALUES (?, ?, ?, ?) ON CONFLICT(origin) DO UPDATE SET "
            "cooldown=max(origins.cooldown,excluded.cooldown)",
            (origin, clock, clock + seconds, clock),
        )
    finally:
        db.close()
