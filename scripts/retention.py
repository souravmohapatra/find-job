"""Preview retention; deletion is invoked only after a successful new backup."""

import argparse
import json
import os
import re
import shutil
import stat
from datetime import UTC, datetime
from pathlib import Path

from recovery import PAYLOADS, private_directory

NAME = re.compile(r"jobfinder-(\d{8}T\d{6}Z)-[0-9a-f]{8}")
FILES = {*PAYLOADS, "manifest.json.gpg", "recipient-check.gpg", "operation.json"}


def eligible(folder: Path, project: str, current: datetime) -> datetime | None:
    """Ignore incomplete, foreign, unexpected or non-private backup directories."""
    matched = NAME.fullmatch(folder.name)
    if not matched:
        return None
    try:
        created = datetime.strptime(matched[1], "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
        if created > current:
            return None
        private_directory(folder)
        if {path.name for path in folder.iterdir()} != FILES:
            return None
        for name in FILES:
            info = (folder / name).lstat()
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.getuid()
                or info.st_mode & 0o077
                or info.st_nlink != 1
                or info.st_size == 0
            ):
                return None
        journal_path = folder / "operation.json"
        if journal_path.stat().st_size > 65536:
            return None
        journal = json.loads(journal_path.read_text())
        if journal.get("project") != project or journal.get("state") != "services_resumed":
            return None
        return created
    except (OSError, ValueError, TypeError, AttributeError):
        return None


def candidates(destination: Path, project: str, *, current: datetime | None = None) -> list[Path]:
    private_directory(destination)
    current = current or datetime.now(UTC)
    entries = []
    for folder in destination.iterdir():
        created = eligible(folder, project, current)
        if created is not None:
            entries.append((created, folder.name, folder))
    entries.sort(reverse=True)
    days, weeks, keep = set(), set(), set()
    for created, _, folder in entries:
        day = created.date()
        week = created.isocalendar()[:2]
        if day not in days and len(days) < 7:
            days.add(day)
            keep.add(folder)
        if week not in weeks and len(weeks) < 4:
            weeks.add(week)
            keep.add(folder)
    return [folder for _, _, folder in entries if folder not in keep]


def prune(destination: Path, project: str) -> int:
    """Caller holds destination lock and has just published a successful backup."""
    removed = 0
    for folder in candidates(destination, project):
        # Recheck immediately before deletion; never follow links or recurse unexpected trees.
        if eligible(folder, project, datetime.now(UTC)) is None:
            raise RuntimeError("Backup changed during retention; pruning stopped.")
        shutil.rmtree(folder)
        removed += 1
    return removed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--project", required=True)
    args = parser.parse_args()
    selected = candidates(args.destination, args.project)
    print("Preview only; no files deleted. Eligible expired snapshots:")
    for folder in selected:
        print(folder.name)
    print(f"Total: {len(selected)}")


if __name__ == "__main__":
    main()
