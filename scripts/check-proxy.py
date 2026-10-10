"""Check cached Squid ACLs in a disposable network-none container; no image pull."""

import subprocess
import time
from pathlib import Path
from uuid import uuid4

from deployment_config import configuration, runtime_security_option

ROOT = Path(__file__).resolve().parents[1]


def docker(*args: str, data: str | None = None) -> str:
    return subprocess.run(
        ["docker", *args], input=data, capture_output=True, text=True, check=True, timeout=30
    ).stdout


def main() -> None:
    config = configuration()
    image = config["services"]["egress-proxy"]["image"]
    name = "jobfinder-acl-check-" + uuid4().hex[:12]
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
            runtime_security_option(config),
            "--entrypoint",
            "setpriv",
            "--mount",
            f"type=bind,src={ROOT / 'deploy/squid.conf'},dst=/etc/squid/squid.conf,readonly",
            image,
            "--no-new-privs",
            "/usr/sbin/squid",
            "-f",
            "/etc/squid/squid.conf",
            "-NYC",
        )
        for attempt in range(30):
            try:
                docker("exec", name, "/bin/bash", "-c", "exec 3<>/dev/tcp/127.0.0.1/3128")
                break
            except subprocess.CalledProcessError:
                if attempt == 29:
                    raise
                time.sleep(0.1)
        status = docker("exec", name, "cat", "/proc/1/status")
        if "NoNewPrivs:\t1" not in status:
            raise RuntimeError("Proxy payload did not enable no-new-privileges")
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
        subprocess.run(["docker", "rm", "-f", name], capture_output=True, check=False)


if __name__ == "__main__":
    main()
