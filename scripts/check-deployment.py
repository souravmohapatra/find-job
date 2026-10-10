"""Check deployment boundaries without fetching images or starting the stack."""

import argparse
import ipaddress
import json
import os
import re
import stat
import subprocess
from pathlib import Path

from deployment_config import configuration, runtime_security_option

ROOT = Path(__file__).resolve().parents[1]


def check(config: dict, *, allow_verified_isolation: bool = False) -> None:
    services = config["services"]
    security_option = runtime_security_option(config)
    expected = {
        "db",
        "migrate",
        "queue-bootstrap",
        "api",
        "worker",
        "ai-worker",
        "fetcher",
        "egress-proxy",
        "ntfy",
        "edge",
    }
    assert set(services) == expected, "Unexpected deployment services"
    secret_scopes = {
        "db": {"db_password"},
        "migrate": {"db_password"},
        "queue-bootstrap": {"db_password"},
        "api": {"db_password", "openrouter_api_key"},
        "ai-worker": {"db_password", "openrouter_api_key"},
        "worker": {"db_password", "fetcher_token", "brave_api_key", "ntfy_publisher_token"},
        "fetcher": {"fetcher_token"},
        "edge": set(),
        "ntfy": set(),
        "egress-proxy": set(),
    }
    for name, service in services.items():
        assert {item["source"] for item in service.get("secrets", [])} == secret_scopes[name], (
            "Unexpected secret exposure"
        )
        assert service.get("network_mode") != "host", "Host networking is development-only"
        assert not service.get("privileged"), "Privileged services are not permitted"
        assert service.get("security_opt") == [security_option], "Inconsistent startup hardening"
        assert service.get("entrypoint", [])[:2] == ["setpriv", "--no-new-privs"], (
            f"Service {name} must enable no-new-privileges before its payload"
        )
        assert service.get("command"), "Wrapped entrypoints require an explicit service command"
        assert all(path.split(":", 1)[0].startswith("/") for path in service.get("tmpfs", [])), (
            "tmpfs options must remain in one quoted absolute mount specification"
        )
        if service.get("healthcheck"):
            assert service["healthcheck"]["test"][:3] == ["CMD", "setpriv", "--no-new-privs"], (
                "Health checks must enable no-new-privileges too"
            )
        assert not service.get("ports") or name == "edge", "Only edge may publish ports"
        assert not any("docker.sock" in str(volume) for volume in service.get("volumes", []))
        if not service.get("build"):
            assert re.fullmatch(r"[^\s]+@sha256:[0-9a-f]{64}", service["image"]), (
                "Pin runtime images"
            )
        assert service["logging"]["options"] == {"max-size": "10m", "max-file": "3"}
    assert set(services["fetcher"]["networks"]) == {"fetch", "fetch_control"}
    assert set(services["egress-proxy"]["networks"]) == {"fetch", "public_outbound"}
    assert set(services["ntfy"]["networks"]) == {"notification"}
    ntfy_image = services["ntfy"]["build"]["args"]["NTFY_IMAGE"]
    assert re.fullmatch(r"binwiederhier/ntfy(?:[:][^@\s]+)?@sha256:[0-9a-f]{64}", ntfy_image)
    assert not ntfy_image.endswith("0" * 64), "Use a real ntfy image digest"
    assert services["ntfy"]["user"] == "10001:10001"
    assert set(services["db"]["networks"]) == {"core"}
    isolation_setting = services["fetcher"]["environment"]["JOBFINDER_FETCH_ISOLATION_VERIFIED"]
    if isolation_setting == "true":
        acceptance_file = ROOT / ".data/fetch_isolation_acceptance.json"
        if not acceptance_file.exists():
            raise AssertionError(
                "JOBFINDER_FETCH_ISOLATION_VERIFIED cannot be 'true' without verified "
                "acceptance evidence (.data/fetch_isolation_acceptance.json)."
            )
        try:
            record = json.loads(acceptance_file.read_text())
            assert record.get("status") == "accepted", "Acceptance record status must be 'accepted'"
        except Exception as error:
            raise AssertionError(f"Invalid fetch isolation acceptance record: {error}") from error
        result = subprocess.run(
            ["bash", str(ROOT / "deploy/fetch-control-rules.sh"), "verify"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise AssertionError(
                f"Active fetch-control firewall rules verification failed:\n"
                f"{result.stderr.strip() or result.stdout.strip()}"
            )
    else:
        assert isolation_setting == "false", (
            "JOBFINDER_FETCH_ISOLATION_VERIFIED must be 'false' unless verified"
        )
    assert {item["source"] for item in services["fetcher"]["secrets"]} == {"fetcher_token"}
    assert "openrouter_api_key" not in {item["source"] for item in services["worker"]["secrets"]}
    for name in ("core", "fetch", "fetch_control", "notification"):
        assert config["networks"][name]["internal"]
    ports = services["edge"]["ports"]
    assert len(ports) == 4
    assert {(port["target"], str(port["published"])) for port in ports} == {
        (8443, "443"),
        (9443, "8443"),
        (8080, "8080"),
        (8081, "8081"),
    }
    origins = json.loads(services["api"]["environment"]["JOBFINDER_ALLOWED_ORIGINS"])
    assert len(origins) == 2 and all(
        re.fullmatch(r"https://[A-Za-z0-9]+(?:[.-][A-Za-z0-9]+)*", value) for value in origins
    ), "Use explicit HTTPS DNS hostnames"
    lan = [
        ipaddress.ip_network(value) for value in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
    ]
    for port in ports:
        address = ipaddress.ip_address(port["host_ip"])
        if port["target"] in (8080, 8081):
            assert str(address) == "127.0.0.1"
        else:
            assert port["target"] in (8443, 9443) and any(address in network for network in lan), (
                "Use an explicit RFC1918 LAN IPv4 address"
            )
    assert (
        services["worker"]["depends_on"]["queue-bootstrap"]["condition"]
        == "service_completed_successfully"
    )
    assert (
        services["ai-worker"]["depends_on"]["queue-bootstrap"]["condition"]
        == "service_completed_successfully"
    )


def check_secrets(config: dict) -> None:
    for name, entry in config["secrets"].items():
        path = Path(entry["file"])
        parent = path.parent.lstat()
        assert (
            stat.S_ISDIR(parent.st_mode)
            and parent.st_uid == os.getuid()
            and not parent.st_mode & 0o077
        ), "Secret directory must be owner-only (0700)"
        info = path.lstat()
        assert stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid(), (
            f"Use an owned regular file for {name}"
        )
        assert info.st_mode & 0o004 and not info.st_mode & 0o022, (
            f"Make {name} readable by container users (0644) inside the private directory"
        )
        # Inspect emptiness only; never print secret contents.
        required = name in {"db_password", "fetcher_token"}
        mode = {
            "openrouter_api_key": "JOBFINDER_INTEGRATION_MODE",
            "brave_api_key": "JOBFINDER_SEARCH_MODE",
            "ntfy_publisher_token": "JOBFINDER_NOTIFICATION_MODE",
        }.get(name)
        if mode:
            required = any(
                service.get("environment", {}).get(mode) == "live"
                for service in config["services"].values()
            )
        value = path.read_bytes().strip()
        if required:
            assert len(value) >= (32 if name == "fetcher_token" else 1), (
                f"Configure {name} before enabling its service"
            )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, help="Actual non-secret deployment parameter file")
    args = parser.parse_args()
    try:
        config = configuration(args.env_file)
        check(config, allow_verified_isolation=bool(args.env_file))
        if args.env_file:
            check_secrets(config)
    except (AssertionError, ValueError, RuntimeError, KeyError, OSError) as error:
        raise SystemExit(f"Deployment check failed: {error}") from None
    print("Compose service, network, port, image-reference and secret-scope checks passed.")
    print(
        "Configuration only; images, secret readability, private ingress "
        "and isolation remain unverified."
    )


if __name__ == "__main__":
    main()
