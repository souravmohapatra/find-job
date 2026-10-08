"""Restore a trusted backup into new isolated volumes; never start application workers."""

import argparse
import os
import subprocess
import time
from pathlib import Path
from uuid import uuid4

from backup import HELPER, run, write_journal
from deployment_config import configuration
from recovery import MAX_PLAINTEXT, VOLUMES, gpg_base, private_directory, verify

# Executed inside a network-none helper as the application's state-volume owner.
EXTRACT = """
import os, sys, tarfile
os.umask(0o077)
count = total = 0
def safe(member, destination):
    global count, total
    count += 1
    total += member.size
    if count > 1000000 or total > 64 * 1024**3:
        raise ValueError('Archive exceeds restore bounds')
    if not (member.isdir() or member.isfile()):
        raise ValueError('Only regular files and directories can be restored')
    member = tarfile.data_filter(member, destination)
    if member is not None:
        member.mode = 0o700 if member.isdir() else member.mode & 0o700
        member.uid = member.gid = member.uname = member.gname = None
    return member
with tarfile.open(fileobj=sys.stdin.buffer, mode='r|') as archive:
    archive.extractall('/restore', filter=safe)
"""


def decrypt_into(path: Path, home: Path, command: list[str], *, timeout: int = 900) -> None:
    """Pipe authenticated-backup contents without writing a plaintext staging file."""
    reader = consumer = None
    try:
        reader = subprocess.Popen(
            [*gpg_base(home), "--max-output", str(MAX_PLAINTEXT), "--decrypt", str(path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        consumer = subprocess.Popen(
            command, stdin=reader.stdout, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        reader.stdout.close()
        status = consumer.wait(timeout=timeout)
        decrypted = reader.wait(timeout=30)
        if status or decrypted:
            raise RuntimeError(f"Restore stream failed (decrypt {decrypted}, restore {status}).")
    finally:
        for process in (consumer, reader):
            if process is not None:
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=10)


def restore(folder: Path, home: Path, destination: Path) -> dict:
    private_directory(destination)
    if any(destination.iterdir()):
        raise ValueError("Restore record directory must be empty.")
    manifest = verify(folder, home)  # Authenticate every payload before creating any resource.
    postgres = configuration()["services"]["db"]["image"]
    for image in (HELPER, postgres):
        run(["docker", "image", "inspect", image])
    identifier = "jobfinder-restore-" + uuid4().hex
    volumes = {name: identifier + "-" + name for name in (*VOLUMES, "postgres")}
    journal = {
        "state": "restoring",
        "source_created_at": manifest.get("created_at"),
        "volumes": volumes,
        "container": identifier,
        "created_volumes": [],
    }
    write_journal(destination, journal)
    helpers = []
    try:
        for logical, volume in volumes.items():
            existing = run(["docker", "volume", "ls", "--format", "{{.Name}}"])
            if volume in existing.splitlines():
                raise ValueError("Restore destination already exists; refusing to reuse it.")
            run(
                ["docker", "volume", "create", "--label", f"jobfinder.restore={identifier}", volume]
            )
            journal["created_volumes"].append(volume)
            write_journal(destination, journal)
            if logical == "postgres":
                continue
            name = identifier + "-" + logical
            helpers.append(name)
            base = [
                "docker",
                "run",
                "--rm",
                "--pull",
                "never",
                "--network",
                "none",
                "--read-only",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges:true",
                "--mount",
                f"type=volume,src={volume},dst=/restore",
            ]
            run(
                [
                    *base,
                    "--cap-add",
                    "CHOWN",
                    HELPER,
                    "python",
                    "-c",
                    "import os; os.chmod('/restore',0o700); os.chown('/restore',10001,10001)",
                ]
            )
            decrypt_into(
                folder / f"{logical}.tar.gpg",
                home,
                [
                    *base,
                    "--name",
                    name,
                    "--user",
                    "10001:10001",
                    "-i",
                    HELPER,
                    "python",
                    "-c",
                    EXTRACT,
                ],
            )
        run(
            [
                "docker",
                "run",
                "-d",
                "--name",
                identifier,
                "--pull",
                "never",
                "--network",
                "none",
                "--label",
                f"jobfinder.restore={identifier}",
                "--mount",
                f"type=volume,src={volumes['postgres']},dst=/var/lib/postgresql/data",
                "-e",
                "POSTGRES_HOST_AUTH_METHOD=trust",
                "-e",
                "POSTGRES_USER=jobfinder",
                "-e",
                "POSTGRES_DB=jobfinder",
                postgres,
                "postgres",
                "-c",
                "listen_addresses=",
            ]
        )
        for _attempt in range(60):
            ready = subprocess.run(
                [
                    "docker",
                    "exec",
                    identifier,
                    "sh",
                    "-c",
                    'test "$(cat /proc/1/comm)" = postgres && pg_isready -U jobfinder',
                ],
                capture_output=True,
                timeout=10,
            )
            if ready.returncode == 0:
                break
            time.sleep(1)
        else:
            raise RuntimeError("Isolated restore database did not become ready.")
        decrypt_into(
            folder / "database.dump.gpg",
            home,
            [
                "docker",
                "exec",
                "-i",
                identifier,
                "pg_restore",
                "-U",
                "jobfinder",
                "-d",
                "jobfinder",
                "--single-transaction",
                "--no-owner",
                "--no-acl",
            ],
        )
        run(
            [
                "docker",
                "exec",
                identifier,
                "psql",
                "-U",
                "jobfinder",
                "-d",
                "jobfinder",
                "-v",
                "ON_ERROR_STOP=1",
                "-Atc",
                "SELECT count(*) FROM pg_catalog.pg_tables",
            ]
        )
        journal["state"] = "restored_isolated"
    except BaseException:
        journal["state"] = "failed_partial_restore"
        raise
    finally:
        cleanup = []
        for name in [*helpers, identifier]:
            try:
                result = subprocess.run(
                    ["docker", "rm", "-f", name], capture_output=True, timeout=30
                )
                if result.returncode and b"No such container" not in result.stderr:
                    cleanup.append(name)
            except (OSError, subprocess.TimeoutExpired):
                cleanup.append(name)
        journal["container_cleanup_failed"] = cleanup
        write_journal(destination, journal)
        if cleanup:
            raise RuntimeError("Restore container cleanup failed; inspect the private journal.")
    return journal


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup", type=Path, required=True)
    parser.add_argument("--gpg-home", type=Path, required=True)
    parser.add_argument("--record-directory", type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    restore(args.backup, args.gpg_home, args.record_directory)
    print("Restored into new isolated volumes; containers removed, application remains stopped.")
    print("Volume names are in the private operation.json. Validate before any deployment cutover.")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, OSError, subprocess.TimeoutExpired) as error:
        raise SystemExit(str(error)) from None
