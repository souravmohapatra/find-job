"""Read Compose configuration without exposing credentials or starting services."""

import json
import os
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def configuration(env_file: Path | None = None) -> dict[str, Any]:
    environment = dict(os.environ)
    if env_file is None:
        # Non-secret template values; this command never starts or pulls anything.
        environment.update(
            LAN_IP="192.168.1.20",
            LAN_HOST="jobs.home.arpa",
            TAILNET_HOST="jobs.example-tailnet.ts.net",
            NTFY_IMAGE="binwiederhier/ntfy@sha256:"
            "f2419f405127afa868f10985c1a41449e673477cee1eb19994339a5ae8b592e7",
            INTEGRATION_MODE="mock",
            SEARCH_MODE="mock",
            NOTIFICATION_MODE="mock",
        )
    result = subprocess.run(
        [
            "docker",
            "compose",
            "--env-file",
            str(env_file or "/dev/null"),
            "-f",
            str(ROOT / "compose.yaml"),
            "config",
            "--format",
            "json",
        ],
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode:
        raise RuntimeError("Compose configuration failed; check required deployment parameters.")
    return json.loads(result.stdout)
