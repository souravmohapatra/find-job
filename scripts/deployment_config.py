"""Read Compose configuration without exposing credentials or starting services."""

import json
import os
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def runtime_security_option(config: dict | None = None) -> str:
    """Share the effective Docker startup setting with disposable helpers."""
    options = (config if config is not None else configuration())["services"]["fetcher"][
        "security_opt"
    ]
    if options not in (["no-new-privileges:true"], ["no-new-privileges:false"]):
        raise ValueError("DOCKER_NO_NEW_PRIVILEGES must be true or false.")
    return str(options[0])


def configuration(env_file: Path | None = None) -> dict[str, Any]:
    environment = dict(os.environ)
    if env_file is None:
        # Non-secret template values; this command never starts or pulls anything.
        environment.update(
            LAN_IP="192.168.1.20",
            LAN_HOST="jobs.home.arpa",
            TAILNET_HOST="jobs.example-tailnet.ts.net",
            NTFY_NETWORK="ntfy_default",
            JOBFINDER_NTFY_URL="http://ntfy:80",
            NTFY_TOPIC="jobfinder",
            APP_LOOPBACK_PORT="8085",
            NOTIFY_LOOPBACK_PORT="8086",
            INTEGRATION_MODE="mock",
            SEARCH_MODE="mock",
            NOTIFICATION_MODE="mock",
            FETCH_ISOLATION_VERIFIED="false",
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
