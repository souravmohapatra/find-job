"""Create a consistent encrypted backup of an already-running Job Finder deployment."""

import argparse
import fcntl
import json
import os
import signal
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from deployment_config import ROOT, configuration
from recovery import (
    VOLUMES,
    ciphertext_record,
    encrypt_bytes,
    encrypt_command,
    private_directory,
    verify,
)

HELPER = "python:3.12-slim@sha256:05cda9777409a9c3ffddd94a4c476b79f0769a0b4857f0c7ed9226b6800b0d6f"
WRITERS = ("edge", "api", "worker", "ai-worker", "fetcher", "ntfy")
RESTART_ORDER = ("ntfy", "fetcher", "api", "ai-worker", "worker", "edge")


def run(command: list[str], *, timeout: int = 60) -> str:
    result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        # Child diagnostics may contain private paths/content. Do not echo them.
        raise RuntimeError(
            f"Backup operation failed (exit {result.returncode}); command: {command[0]}."
        )
    return result.stdout


def rows(raw: str) -> list[dict]:
    if not raw.strip():
        return []
    return (
        json.loads(raw)
        if raw.lstrip().startswith("[")
        else [json.loads(line) for line in raw.splitlines()]
    )


def write_journal(folder: Path, journal: dict) -> None:
    pending = folder / "operation.json.next"
    descriptor = os.open(pending, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        stream.write(json.dumps(journal) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    pending.replace(folder / "operation.json")
    sync_directory(folder)


def sync_directory(folder: Path) -> None:
    descriptor = os.open(folder, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def archive_command(volume: str, name: str) -> list[str]:
    return [
        "docker",
        "run",
        "--rm",
        "--name",
        name,
        "--pull",
        "never",
        "--network",
        "none",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges:true",
        "--user",
        "10001:10001",
        "--mount",
        f"type=volume,src={volume},dst=/source,readonly",
        HELPER,
        "python",
        "-c",
        "import sys,tarfile; t=tarfile.open(fileobj=sys.stdout.buffer,mode='w|'); "
        "t.add('/source',arcname='.'); t.close()",
    ]


def validate_layout(config: dict, states: list[dict]) -> dict:
    """Bind the requested volumes to actual containers, not merely current YAML."""
    by_service = {row["Service"]: row for row in states}
    if not set((*WRITERS, "db")).issubset(by_service):
        raise ValueError("Create the full deployment before taking a complete backup.")
    evidence = {}
    for service in (*WRITERS, "db"):
        identifier = by_service[service]["ID"]
        container = json.loads(run(["docker", "inspect", identifier]))[0]
        labels = container["Config"].get("Labels", {})
        if (
            labels.get("com.docker.compose.project") != config["name"]
            or labels.get("com.docker.compose.service") != service
        ):
            raise ValueError("Container identity changed; no backup started.")
        actual = {
            entry["Destination"]: entry.get("Name")
            for entry in container["Mounts"]
            if entry["Type"] == "volume"
        }
        for mount in config["services"][service].get("volumes", []):
            if mount["type"] == "volume":
                expected = config["volumes"][mount["source"]]["name"]
                if actual.get(mount["target"]) != expected:
                    raise ValueError(
                        "Running volume layout differs from Compose; reconcile it first."
                    )
        evidence[service] = {"container_id": identifier, "image_id": container["Image"]}
    return evidence


def capture(compose: list[str], config: dict, folder: Path, home: Path, recipient: str) -> dict:
    """Capture state and resume originally active services, including on failure."""
    states = rows(run([*compose, "ps", "--all", "--format", "json"]))
    if sum(row["Service"] == "db" and row["State"] == "running" for row in states) != 1:
        raise ValueError("Exactly one running deployment database is required.")
    if any(
        row["Service"] in {"migrate", "queue-bootstrap"} and row["State"] == "running"
        for row in states
    ):
        raise ValueError("Wait for deployment migrations/bootstrap to finish.")
    if len({row["Service"] for row in states}) != len(states):
        raise ValueError("Backup currently requires one container per service.")
    if any(
        row["Service"] in WRITERS
        and row["State"] not in {"running", "restarting", "exited", "created"}
        for row in states
    ):
        raise ValueError("Resolve paused or transitional service states before backup.")
    layout = validate_layout(config, states)
    active = {row["Service"] for row in states if row["State"] in {"running", "restarting"}}
    resume = [name for name in RESTART_ORDER if name in active]
    volumes = {name: config["volumes"][name]["name"] for name in VOLUMES}
    for volume in volumes.values():
        run(
            ["docker", "volume", "inspect", volume]
        )  # Never silently back up newly-created empty volumes.
    run(["docker", "image", "inspect", HELPER])
    encrypt_bytes(
        b"JobFinder backup recipient readiness", folder / "recipient-check.gpg", home, recipient
    )
    journal = {
        "project": config["name"],
        "resume_services": resume,
        "state": "pausing",
        "runtime": layout,
    }
    write_journal(folder, journal)
    helper_names: list[str] = []
    stopped = False
    try:
        stopped = True  # Even partial stop failure must reach recovery.
        run([*compose, "stop", "--timeout", "45", *WRITERS], timeout=180)
        remaining = rows(run([*compose, "ps", "--all", "--format", "json"]))
        if any(
            row["Service"] in WRITERS and row["State"] not in {"exited", "created"}
            for row in remaining
        ):
            raise RuntimeError("Writers did not stop; no consistent backup can be claimed.")
        payloads = {}
        target = folder / "database.dump.gpg"
        encrypt_command(
            [
                *compose,
                "exec",
                "-T",
                "db",
                "pg_dump",
                "-U",
                "jobfinder",
                "-d",
                "jobfinder",
                "--format=custom",
                "--no-owner",
                "--no-acl",
            ],
            target,
            home,
            recipient,
        )
        payloads[target.name] = ciphertext_record(target)
        for logical, volume in volumes.items():
            name = "jobfinder-backup-" + uuid4().hex[:12]
            helper_names.append(name)
            target = folder / f"{logical}.tar.gpg"
            command = archive_command(volume, name)
            encrypt_command(command, target, home, recipient)
            payloads[target.name] = ciphertext_record(target)
        final_states = rows(run([*compose, "ps", "--all", "--format", "json"]))
        if any(
            row["Service"] in WRITERS and row["State"] not in {"exited", "created"}
            for row in final_states
        ):
            raise RuntimeError(
                "A writer restarted during backup; discard this incomplete snapshot."
            )
        return {
            "format": 1,
            "project": config["name"],
            "created_at": datetime.now(UTC).isoformat(),
            "payloads": payloads,
            "runtime": layout,
        }
    finally:
        cleanup_failed = []
        for name in helper_names:
            try:
                subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=30)
            except (OSError, subprocess.TimeoutExpired):
                cleanup_failed.append(name)
        failures = []
        if stopped:
            for service in resume:
                try:
                    run([*compose, "start", "--wait", "--wait-timeout", "60", service], timeout=90)
                except (RuntimeError, OSError, subprocess.TimeoutExpired):
                    failures.append(service)
        journal["state"] = "restart_failed" if failures else "services_resumed"
        journal["restart_failed"] = failures
        journal["helper_cleanup_failed"] = cleanup_failed
        write_journal(folder, journal)
        if failures:
            raise RuntimeError("Backup service restart failed: " + ", ".join(failures))


def interrupted(signum: int, frame: object) -> None:
    raise InterruptedError("Backup interrupted; attempting service recovery.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--destination", type=Path)
    parser.add_argument("--gpg-home", type=Path, required=True)
    parser.add_argument("--recipient")
    parser.add_argument(
        "--verify", type=Path, help="Verify an encrypted backup without restoring it"
    )
    args = parser.parse_args()
    os.umask(0o077)
    if args.verify:
        verify(args.verify.resolve(), args.gpg_home.resolve())
        print("Encrypted manifest, ciphertext hashes and all payload integrity checks passed.")
        return
    if not all((args.env_file, args.destination, args.recipient)):
        parser.error("Backup needs --env-file, --destination and --recipient.")
    destination = args.destination.resolve()
    private_directory(destination)
    home = args.gpg_home.resolve()
    private_directory(home)
    config = configuration(args.env_file.resolve())
    compose = [
        "docker",
        "compose",
        "--env-file",
        str(args.env_file.resolve()),
        "-f",
        str(ROOT / "compose.yaml"),
        "-p",
        config["name"],
    ]
    lock_dir = ROOT / ".data"
    lock_dir.mkdir(mode=0o700, exist_ok=True)
    private_directory(lock_dir)
    with (lock_dir / "backup.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        signal.signal(signal.SIGTERM, interrupted)
        name = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
        pending = destination / (".incomplete-" + name)
        pending.mkdir(mode=0o700)
        manifest = capture(compose, config, pending, home, args.recipient)
        encrypt_bytes(
            json.dumps(manifest).encode(), pending / "manifest.json.gpg", home, args.recipient
        )
        final = destination / ("jobfinder-" + name)
        sync_directory(pending)
        pending.rename(final)
        sync_directory(destination)
        print(f"Encrypted backup completed: {final.name}")
        print("Back up secret files and the decryption key separately. Run a restore drill.")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, OSError, subprocess.TimeoutExpired) as error:
        raise SystemExit(str(error)) from None
