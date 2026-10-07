"""Validate private ntfy ACLs in a disposable network-none container; no real recipients."""

import base64
import json
import re
import subprocess
import time
from pathlib import Path
from uuid import uuid4

from deployment_config import configuration

ROOT = Path(__file__).resolve().parents[1]


def docker(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", *args], capture_output=True, text=True, check=check, timeout=30
    )


def main() -> None:
    name = "jobfinder-ntfy-check-" + uuid4().hex[:12]
    started = False
    try:
        docker(
            "run",
            "-d",
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
            "--tmpfs",
            "/tmp:size=16m,mode=1777",
            "--tmpfs",
            "/var/lib/ntfy:size=32m,uid=10001,gid=10001,mode=0700",
            "--env",
            "NTFY_BASE_URL=https://synthetic.example:8443",
            "--mount",
            f"type=bind,src={ROOT / 'deploy/ntfy.yml'},dst=/etc/ntfy/server.yml,readonly",
            "jobfinder-ntfy:local",
            "serve",
            "--config",
            "/etc/ntfy/server.yml",
        )
        started = True
        for attempt in range(30):
            health = docker(
                "exec",
                name,
                "wget",
                "-q",
                "-T",
                "2",
                "-O",
                "-",
                "http://127.0.0.1:8080/v1/health",
                check=False,
            )
            if health.returncode == 0:
                assert json.loads(health.stdout)["healthy"] is True
                break
            if attempt == 29:
                raise RuntimeError("Disposable ntfy did not become healthy")
            time.sleep(0.2)
        health_command = configuration()["services"]["ntfy"]["healthcheck"]["test"][1]
        docker("exec", name, "/bin/sh", "-c", health_command)
        password = "synthetic-disposable-password"
        for user, permission in (("publisher", "write-only"), ("reader", "read-only")):
            docker("exec", "-e", f"NTFY_PASSWORD={password}", name, "ntfy", "user", "add", user)
            docker("exec", name, "ntfy", "access", user, "jobfinder", permission)
        token_output = docker("exec", name, "ntfy", "token", "add", "publisher")
        token = re.search(r"\btk_[A-Za-z0-9]+\b", token_output.stdout + token_output.stderr)
        assert token is not None, "ntfy did not issue a publisher token"
        publisher = "Bearer " + token.group()
        reader = "Basic " + base64.b64encode(f"reader:{password}".encode()).decode()

        def request(
            path: str, authorization: str | None = None, publish: bool = False
        ) -> tuple[int, str]:
            args = ["exec", name, "wget", "-S", "-T", "3", "-O", "-"]
            if authorization:
                args.extend(["--header", "Authorization: " + authorization])
            if publish:
                args.extend(["--post-data", "Synthetic isolated notification"])
            args.append("http://127.0.0.1:8080/" + path)
            result = docker(*args, check=False)
            statuses = re.findall(r"HTTP/\d\.\d (\d{3})", result.stderr)
            assert statuses, "No ntfy HTTP status received"
            return int(statuses[-1]), result.stdout

        assert request("jobfinder", publish=True)[0] in {401, 403}
        assert request("jobfinder/json?poll=1")[0] in {401, 403}
        status, body = request("jobfinder", publisher, publish=True)
        receipt = json.loads(body)
        assert status == 200 and receipt["topic"] == "jobfinder" and receipt["id"]
        assert request("jobfinder/json?poll=1", publisher)[0] == 403
        assert request("other-topic", publisher, publish=True)[0] == 403
        assert request("jobfinder", reader, publish=True)[0] == 403
        status, body = request("jobfinder/json?poll=1", reader)
        assert status == 200
        assert any(json.loads(line).get("id") == receipt["id"] for line in body.splitlines())
        print(
            "ntfy health, anonymous denial, publish-only token, "
            "reader-only access and cached receipt passed."
        )
        print(
            "Disposable server only: no published ports, network access, "
            "real credentials or recipients."
        )
    finally:
        if started:
            docker("rm", "-f", name)


if __name__ == "__main__":
    main()
