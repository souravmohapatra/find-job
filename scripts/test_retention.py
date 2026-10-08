"""Retention checks use disposable synthetic directories, never real backups."""

import json
import os
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import backup
from retention import FILES, candidates, prune


class RetentionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="jobfinder-retention-test-")
        self.root = Path(self.temp.name)
        self.current = datetime(2026, 10, 8, 12, tzinfo=UTC)

    def tearDown(self):
        self.temp.cleanup()

    def snapshot(self, created, *, project="synthetic", suffix="00000000"):
        folder = self.root / ("jobfinder-" + created.strftime("%Y%m%dT%H%M%SZ") + "-" + suffix)
        folder.mkdir(mode=0o700)
        for name in FILES:
            path = folder / name
            path.write_bytes(b"synthetic encrypted bytes")
            path.chmod(0o600)
        (folder / "operation.json").write_text(
            json.dumps({"project": project, "state": "services_resumed"})
        )
        return folder

    def test_seven_distinct_days_and_four_distinct_iso_weeks(self):
        snapshots = [self.snapshot(self.current - timedelta(days=i)) for i in range(40)]
        expired = set(candidates(self.root, "synthetic", current=self.current))
        # Oct 8..2 are daily; weekly representatives are Oct 8, Oct 4, Sep 27, Sep 20.
        kept = {snapshots[i] for i in (0, 1, 2, 3, 4, 5, 6, 11, 18)}
        self.assertEqual(set(snapshots) - expired, kept)
        with patch("retention.datetime", wraps=datetime) as clock:
            clock.now.return_value = self.current
            self.assertEqual(prune(self.root, "synthetic"), 31)
        self.assertEqual(set(self.root.iterdir()), kept)

    def test_multiple_same_day_backups_keep_the_newest(self):
        older = self.snapshot(self.current - timedelta(hours=2))
        newer = self.snapshot(self.current - timedelta(hours=1))
        self.assertEqual(candidates(self.root, "synthetic", current=self.current), [older])
        self.assertTrue(newer.exists())

    def test_iso_week_year_boundary(self):
        current = datetime(2027, 1, 5, tzinfo=UTC)
        snapshots = [self.snapshot(current - timedelta(days=i * 7)) for i in range(8)]
        # Seven available daily dates already cover the newest seven weekly dates.
        self.assertEqual(candidates(self.root, "synthetic", current=current), [snapshots[-1]])

    def test_foreign_incomplete_future_and_unexpected_paths_are_untouched(self):
        protected = []
        for i in range(8):
            self.snapshot(self.current - timedelta(days=i))
        protected.append(self.snapshot(self.current - timedelta(days=60), project="another"))
        protected.append(self.snapshot(self.current + timedelta(days=1)))
        odd = self.snapshot(self.current - timedelta(days=61))
        (odd / "unexpected.txt").write_text("never delete")
        protected.append(odd)
        unsafe = self.snapshot(self.current - timedelta(days=62))
        (unsafe / "manifest.json.gpg").chmod(0o644)
        protected.append(unsafe)
        incomplete = self.root / ".incomplete-20200101T000000Z-00000000"
        incomplete.mkdir(mode=0o700)
        protected.append(incomplete)
        self.assertTrue(
            set(protected).isdisjoint(candidates(self.root, "synthetic", current=self.current))
        )
        prune(self.root, "synthetic")
        self.assertTrue(all(path.exists() for path in protected))

    def test_symlink_and_hardlink_payloads_never_pruned(self):
        target = self.root / "unrelated"
        target.write_text("preserve")
        target.chmod(0o600)
        for offset, symbolic in [(50, True), (60, False)]:
            folder = self.snapshot(self.current - timedelta(days=offset))
            payload = folder / "manifest.json.gpg"
            payload.unlink()
            if symbolic:
                payload.symlink_to(target)
            else:
                os.link(target, payload)
        self.assertEqual(candidates(self.root, "synthetic", current=self.current), [])
        self.assertEqual(prune(self.root, "synthetic"), 0)
        self.assertEqual(target.read_text(), "preserve")

    def test_failed_backup_never_invokes_retention(self):
        home = self.root / "keyring"
        home.mkdir(mode=0o700)
        destination = self.root / "backups"
        destination.mkdir(mode=0o700)
        args = [
            "backup.py",
            "--env-file",
            str(self.root / "deploy.env"),
            "--destination",
            str(destination),
            "--gpg-home",
            str(home),
            "--recipient",
            "0" * 40,
            "--retain",
        ]
        with (
            patch("sys.argv", args),
            patch.object(backup, "configuration", return_value={"name": "synthetic"}),
            patch.object(backup, "capture", side_effect=RuntimeError("synthetic capture failure")),
            patch.object(backup, "prune") as retention,
            patch.object(backup.signal, "signal"),
            patch.object(backup.os, "umask"),
        ):
            with self.assertRaisesRegex(RuntimeError, "synthetic capture failure"):
                backup.main()
            retention.assert_not_called()
        self.assertFalse(any(path.name.startswith("jobfinder-") for path in destination.iterdir()))


if __name__ == "__main__":
    unittest.main()
