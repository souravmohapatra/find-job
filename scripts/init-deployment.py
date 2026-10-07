"""Create private deployment inputs without replacing existing files or reading .env."""

import os
import secrets
import stat
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    folder = ROOT / ".secrets"
    folder.mkdir(mode=0o700, exist_ok=True)
    info = folder.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise SystemExit("Use an owner-only .secrets directory (0700); no files were changed.")
    for name in (
        "db_password",
        "fetcher_token",
        "openrouter_api_key",
        "brave_api_key",
        "ntfy_publisher_token",
    ):
        value = secrets.token_urlsafe(32) if name in {"db_password", "fetcher_token"} else ""
        try:
            descriptor = os.open(folder / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        except FileExistsError:
            continue
        with os.fdopen(descriptor, "w") as stream:
            # Directory privacy protects host access; container mounts need read permission.
            os.fchmod(stream.fileno(), 0o644)
            stream.write(value + "\n")
    target = ROOT / "deploy/.env"
    try:
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        pass
    else:
        with os.fdopen(descriptor, "w") as stream:
            stream.write((ROOT / "deploy/.env.example").read_text())
    print("Deployment input files prepared; existing files and their permissions preserved.")
    print(
        "Set host parameters/image digest in deploy/.env. Provider and publisher files start empty."
    )
    print(
        "Existing secrets must be container-readable inside the private directory; run preflight."
    )


if __name__ == "__main__":
    main()
