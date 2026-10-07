"""Check cached Squid ACLs in a disposable network-none container; no image pull."""

import json
import subprocess
import time
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


def docker(*args: str, data: str | None = None) -> str:
    return subprocess.run(
        ["docker", *args], input=data, capture_output=True, text=True, check=True, timeout=30
    ).stdout


def main() -> None:
    config = json.loads(
        docker(
            "compose",
            "-f",
            str(ROOT / "compose.yaml"),
            "-f",
            str(ROOT / "compose.fetch.yaml"),
            "config",
            "--format",
            "json",
        )
    )
    image = config["services"]["egress-proxy"]["image"]
    name = "jobfinder-acl-check-" + uuid4().hex[:12]
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
            "--user",
            "13:13",
            "--read-only",
            "--tmpfs",
            "/tmp:size=16m,mode=1777",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges:true",
            "--entrypoint",
            "/usr/sbin/squid",
            "--mount",
            f"type=bind,src={ROOT / 'deploy/squid.conf'},dst=/etc/squid/squid.conf,readonly",
            image,
            "-f",
            "/etc/squid/squid.conf",
            "-NYC",
        )
        started = True
        for attempt in range(30):
            try:
                docker("exec", name, "/bin/bash", "-c", "exec 3<>/dev/tcp/127.0.0.1/3128")
                break
            except subprocess.CalledProcessError:
                if attempt == 29:
                    raise
                time.sleep(0.1)
        hosts = [
            "127.0.0.1",
            "10.0.0.1",
            "172.16.0.1",
            "192.168.0.1",
            "169.254.169.254",
            "100.64.0.1",
            "0.0.0.0",
            "[::1]",
            "[fc00::1]",
            "[fe80::1]",
            "[2001:db8::1]",
            "[::ffff:127.0.0.1]",
        ]
        cases = [("GET", f"http://{host}/", 403) for host in hosts]
        cases += [
            ("GET", "http://1.1.1.1/", 503),
            ("GET", "http://[2606:4700::1111]/", 503),
            ("CONNECT", "127.0.0.1:443", 403),
            ("CONNECT", "[::1]:443", 403),
            ("CONNECT", "1.1.1.1:80", 403),
            ("CONNECT", "1.1.1.1:443", 503),
            ("GET", "http://1.1.1.1:8080/", 403),
            ("POST", "http://1.1.1.1/", 403),
        ]
        for method, url, status in cases:
            response = docker(
                "exec",
                "-i",
                name,
                "/bin/bash",
                "-c",
                "exec 3<>/dev/tcp/127.0.0.1/3128; cat >&3; head -n 12 <&3",
                data=f"{method} {url} HTTP/1.1\r\nHost: example.com\r\nConnection: close\r\n\r\n",
            )
            expected = "ERR_ACCESS_DENIED" if status == 403 else "ERR_CONNECT_FAIL"
            if f" {status} " not in response.splitlines()[0] or expected not in response:
                raise RuntimeError(f"Unexpected ACL result for {method} {url}: {response[:1000]}")
        print(f"{len(cases)} ACL checks passed; public connections lack a route by design.")
        print("This does not validate Compose bypass resistance or DNS rebinding.")
    finally:
        if started:
            docker("rm", "-f", name)


if __name__ == "__main__":
    main()
