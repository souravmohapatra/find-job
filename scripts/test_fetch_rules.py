"""Mocked-iptables tests for the fetch-control installer.

Covers first install, identical reinstall, stale-rule reinstall, transactional
rollback on apply failure, rollback removal and drift-detected verification —
without touching the real firewall. Run: python3 scripts/test_fetch_rules.py
"""

import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path
from subprocess import run

ROOT = Path(__file__).resolve().parents[1]

FAKE_IPTABLES = r"""\
#!/usr/bin/env bash
# Minimal iptables emulation over a file per chain.
STATE="$FAKE_STATE"
mode=$(cat "$STATE/mode" 2>/dev/null || echo normal)
if [ "$1" = "-S" ]; then
  [ -f "$STATE/$2" ] && cat "$STATE/$2"
  exit 0
fi
if [ "$1" = "-L" ]; then exit 0; fi
if [ "$1" = "-I" ]; then
  chain=$2; pos=$3; shift 3
  if [ "$mode" = "fail-inserts" ]; then echo "permission denied" >&2; exit 1; fi
  if [[ "$mode" == fail-after-* ]]; then
    limit=${mode#fail-after-}
    count=$(cat "$STATE/insert_count" 2>/dev/null || echo 0)
    count=$((count + 1))
    echo "$count" > "$STATE/insert_count"
    if [ "$count" -gt "$limit" ]; then
      echo "permission denied at insert $count" >&2
      exit 1
    fi
  fi
  file="$STATE/$chain"
  touch "$file"
  # Real iptables renders bare IPv4 sources/destinations with a /32 prefix.
  rendered=$(echo "$*" | sed -E 's/(-[sd] )([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+) /\1\2\/32 /g')
  { head -n $((pos - 1)) "$file"; echo "-A $chain $rendered"; tail -n +"$pos" "$file"; } \
    > "$file.tmp" 2>/dev/null && mv "$file.tmp" "$file"
  exit 0
fi
if [ "$1" = "-D" ]; then
  chain=$2; shift 2
  file="$STATE/$chain"
  # grep exits 1 when every line matched (nothing remains): still a successful delete.
  grep -vF -- "-A $chain $*" "$file" > "$file.tmp"
  status=$?
  [ "$status" -eq 0 ] || [ "$status" -eq 1 ] || { echo "grep failed" >&2; exit 1; }
  mv "$file.tmp" "$file"
  exit 0
fi
echo "unsupported invocation" >&2
exit 1
"""

FAKE_DOCKER = """\
#!/usr/bin/env bash
# Emulates exactly the invocations deploy/fetch-control-rules.sh makes.
mode=$(cat "$FAKE_STATE/mode" 2>/dev/null || echo normal)
if [ "$1" = "network" ] && [ "$2" = "inspect" ]; then
  net=$3; fmt=$5
  case "$net" in
    jobfinder_fetch_control) id=fcnet00000001 ;;
    jobfinder_fetch) id=fchnet00000002 ;;
    *) exit 1 ;;
  esac
  case "$fmt" in
    *Id*) echo "$id" ;;
    *Internal*) echo "true" ;;
    *) exit 1 ;;
  esac
  exit 0
fi
if [ "$1" = "compose" ]; then
  service=$6
  case "$service" in
    fetcher) echo "c-fetcher" ;;
    egress-proxy) echo "c-proxy" ;;
    *) exit 1 ;;
  esac
  exit 0
fi
if [ "$1" = "inspect" ]; then
  container=$2; fmt=$4
  fetcher_fc=172.30.0.10
  if [ "$mode" = "drift" ]; then fetcher_fc=172.30.0.99; fi
  if [ "$container" = "c-fetcher" ]; then
    case "$fmt" in
      *jobfinder_fetch_control*) echo "$fetcher_fc" ;;
      *jobfinder_fetch*) echo "172.31.0.10" ;;
      *) echo "$fetcher_fc" ;;
    esac
    exit 0
  fi
  if [ "$container" = "c-proxy" ]; then echo "172.31.0.20"; exit 0; fi
  exit 1
fi
exit 1
"""


class FetchRulesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="jobfinder-fc-rules-test-")
        self.state = Path(self.temp.name) / "state"
        self.bin_dir = Path(self.temp.name) / "bin"
        self.bin_dir.mkdir()
        self.state.mkdir()
        (self.state / "mode").write_text("normal")
        for name, body in [("iptables", FAKE_IPTABLES), ("docker", FAKE_DOCKER)]:
            path = self.bin_dir / name
            path.write_text(body)
            path.chmod(stat.S_IRWXU)
        (self.state / "bridge-nf").write_text("1")

    def tearDown(self):
        self.temp.cleanup()

    def script(self, *args: str) -> "subprocess.CompletedProcess[str]":
        env = dict(
            os.environ,
            PATH=f"{self.bin_dir}:{os.environ['PATH']}",
            FAKE_STATE=str(self.state),
            BRIDGE_NF_PROC=str(self.state / "bridge-nf"),
        )
        return run(
            [str(ROOT / "deploy/fetch-control-rules.sh"), *args],
            capture_output=True,
            text=True,
            env=env,
            cwd=ROOT,
            check=False,
        )

    def counts(self) -> str:
        docker_user = (
            (self.state / "DOCKER-USER").read_text().splitlines()
            if (self.state / "DOCKER-USER").exists()
            else []
        )
        iptable = (
            (self.state / "INPUT").read_text().splitlines()
            if (self.state / "INPUT").exists()
            else []
        )
        return f"{len(docker_user)} {len(iptable)}"

    def test_first_install_creates_exactly_ten_rules(self):
        result = self.script("install")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.counts(), "8 2")
        self.assertIn("-p tcp", self.state_reads())

    def state_reads(self) -> str:
        return (self.state / "DOCKER-USER").read_text() + (
            self.state / "INPUT"
        ).read_text()

    def test_identical_reinstall_is_idempotent(self):
        self.script("install")
        result = self.script("install")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.counts(), "8 2")
        self.assertIn("already present", result.stdout)

    def test_stale_rules_are_replaced_not_stacked(self):
        self.script("install")
        (self.state / "mode").write_text("drift")
        result = self.script("install")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.counts(), "8 2")
        self.assertIn("172.30.0.99/32", self.state_reads())
        self.assertNotIn("172.30.0.10", self.state_reads())

    def test_apply_failure_rolls_back_partially_installed_rules(self):
        # Test partial failure after 4 rules were successfully inserted.
        (self.state / "mode").write_text("fail-after-4")
        result = self.script("install")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("rolled back", result.stderr)
        self.assertEqual(self.counts(), "0 0")

    def test_initial_apply_failure_rolls_back(self):
        (self.state / "mode").write_text("fail-inserts")
        result = self.script("install")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("rolled back", result.stderr)
        self.assertEqual(self.counts(), "0 0")

    def test_rollback_removes_all_marked_rules(self):
        self.script("install")
        result = self.script("rollback")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.counts(), "0 0")

    def test_verify_detects_address_drift(self):
        self.script("install")
        (self.state / "mode").write_text("drift")
        result = self.script("verify")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("address changed", result.stderr)


if __name__ == "__main__":
    unittest.main()
