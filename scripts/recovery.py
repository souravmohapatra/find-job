"""Streaming encrypted backup primitives. Never stage plaintext application data."""

import hashlib
import json
import os
import re
import stat
import subprocess
from pathlib import Path
from typing import Any

VOLUMES = ("documents", "caddy_data", "caddy_config", "fetch_state")
PAYLOADS = ("database.dump.gpg", *(f"{name}.tar.gpg" for name in VOLUMES))
MAX_PLAINTEXT = 64 * 1024**3


def private_directory(path: Path) -> None:
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError("Use an owned, non-symlink directory with mode 0700.")


def gpg_base(home: Path) -> list[str]:
    private_directory(home)
    return [
        "gpg",
        "--no-options",
        "--homedir",
        str(home),
        "--batch",
        "--no-tty",
        "--no-auto-key-retrieve",
        "--auto-key-locate",
        "clear",
    ]


def encrypt_args(home: Path, recipient: str) -> list[str]:
    if not re.fullmatch(r"(?:[A-Fa-f0-9]{40}|[A-Fa-f0-9]{64})", recipient):
        raise ValueError("Use the full backup recipient fingerprint.")
    return [
        *gpg_base(home),
        "--trust-model",
        "always",
        "--compress-algo",
        "none",
        "--recipient",
        recipient,
        "--encrypt",
        "--output",
        "-",
    ]


def ciphertext_record(path: Path) -> dict[str, Any]:
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return {"size": path.stat().st_size, "sha256": digest}


def encrypt_bytes(data: bytes, target: Path, home: Path, recipient: str) -> None:
    args = encrypt_args(home, recipient)
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as output:
        result = subprocess.run(
            args, input=data, stdout=output, stderr=subprocess.DEVNULL, timeout=60
        )
        if result.returncode:
            raise RuntimeError(f"Backup encryption failed (exit {result.returncode}).")
        output.flush()
        os.fsync(output.fileno())


def encrypt_command(
    command: list[str], target: Path, home: Path, recipient: str, *, timeout: int = 900
) -> None:
    args = encrypt_args(home, recipient)
    producer = None
    cipher = None
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as output:
            producer = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            assert producer.stdout is not None
            cipher = subprocess.Popen(
                args, stdin=producer.stdout, stdout=output, stderr=subprocess.DEVNULL
            )
            producer.stdout.close()
            cipher_status = cipher.wait(timeout=timeout)
            producer_status = producer.wait(timeout=30)
            if cipher_status or producer_status:
                raise RuntimeError(
                    f"Backup stream failed (source exit {producer_status}, "
                    f"encryption exit {cipher_status})."
                )
            output.flush()
            os.fsync(output.fileno())
    finally:
        for process in (cipher, producer):
            if process is not None:
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=10)


def verify(folder: Path, home: Path) -> dict[str, Any]:
    """Decrypt metadata, verify ciphertext hashes, then authenticate all payloads to /dev/null."""
    private_directory(folder)
    manifest_path = folder / "manifest.json.gpg"
    if not stat.S_ISREG(manifest_path.lstat().st_mode):
        raise ValueError("The encrypted manifest must be a regular file.")
    result = subprocess.run(
        [*gpg_base(home), "--max-output", "65536", "--decrypt", str(manifest_path)],
        capture_output=True,
        timeout=60,
    )
    if result.returncode:
        raise ValueError("The encrypted manifest could not be authenticated/decrypted.")
    try:
        manifest = json.loads(result.stdout)
        if manifest["format"] != 1 or set(manifest["payloads"]) != set(PAYLOADS):
            raise ValueError
        for name in PAYLOADS:
            record = manifest["payloads"][name]
            path = folder / name
            if not stat.S_ISREG(path.lstat().st_mode) or ciphertext_record(path) != record:
                raise ValueError
    except (KeyError, TypeError, ValueError, OSError):
        raise ValueError("Backup manifest or encrypted payload checks failed.") from None
    for name in PAYLOADS:
        result = subprocess.run(
            [*gpg_base(home), "--max-output", str(MAX_PLAINTEXT), "--decrypt", str(folder / name)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=900,
        )
        if result.returncode:
            raise ValueError(f"Encrypted payload verification failed: {name}.")
    return manifest
