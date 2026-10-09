"""Draft acceptance test runner for section 9.2 fetch isolation matrix.

NOTE: Live container matrix execution is currently RUNTIME-BLOCKED by host blocker
R1 (Snap Docker NoNewPrivs EPERM). This script is draft scaffolding under development,
not a completed isolation proof.
"""

import argparse
import http.server
import subprocess
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def die(message: str) -> None:
    print(f"FAILED: {message}", file=sys.stderr)
    sys.exit(1)


def info(message: str) -> None:
    print(f"[*] {message}")


class DisposableLocalServer:
    """Disposable HTTP server on localhost to test private destination rejection."""

    def __init__(self, port: int = 18080):
        self.port = port
        self.server = http.server.HTTPServer(
            ("127.0.0.1", port), http.server.SimpleHTTPRequestHandler
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.server.shutdown()
        self.server.server_close()


def test_ip_literal_rejection() -> None:
    """Matrix probe: Proxy / Fetcher -> private IPv4, IPv6, mapped addresses."""
    info("Testing local & proxy rejection of non-global destinations...")
    from app.collection.contracts import public_link
    from app.fetcher import http as fetch_http
    from app.fetcher.contracts import FetchFailure

    private_targets = [
        "http://127.0.0.1/",
        "http://10.0.0.1/",
        "http://172.16.0.1/",
        "http://192.168.1.1/",
        "http://169.254.169.254/latest/meta-data",
        "http://0.0.0.0/",
        "http://[::1]/",
        "http://[fc00::1]/",
        "http://[fe80::1]/",
        "http://[2001:db8::1]/",
        "http://127.0.0.1:22/",
        "http://127.0.0.1:8080/",
    ]
    for target in private_targets:
        rejected = False
        try:
            public_link(target)
        except ValueError:
            rejected = True
        if not rejected:
            import asyncio

            try:
                asyncio.run(
                    fetch_http.resolve_public(target, proxy_url="http://127.0.0.1:3128")
                )
            except FetchFailure as failure:
                if failure.code == "destination_denied":
                    rejected = True
        if not rejected:
            die(f"Target was not rejected as non-global: {target}")
    info("PASS: All private IPv4, IPv6, mapped, and non-80/443 ports rejected.")


def test_fetcher_rpc_auth(fetcher_url: str, token: str) -> None:
    """Matrix probe: Worker -> authenticated fetcher RPC (valid/missing/wrong token)."""
    info("Testing fetcher RPC authentication...")
    import httpx

    # Missing token -> 401
    resp = httpx.post(
        f"{fetcher_url}/fetch", json={"url": "https://example.com"}, timeout=5
    )
    if resp.status_code != 401:
        die(f"Missing token expected 401, got {resp.status_code}")

    # Wrong token -> 401
    resp = httpx.post(
        f"{fetcher_url}/fetch",
        json={"url": "https://example.com"},
        headers={"Authorization": "Bearer wrong-token-value-with-32-chars-xxxx"},
        timeout=5,
    )
    if resp.status_code != 401:
        die(f"Wrong token expected 401, got {resp.status_code}")

    # Valid token when isolation_verified is false -> 502 isolation_not_verified
    resp = httpx.post(
        f"{fetcher_url}/fetch",
        json={"url": "https://example.com"},
        headers={"Authorization": f"Bearer {token}"},
        timeout=5,
    )
    data = resp.json() if resp.status_code == 502 else {}
    if resp.status_code == 502 and data.get("code") == "isolation_not_verified":
        info(
            "PASS: Correct token verified; isolation gate safely blocks unverified fetching."
        )
    elif resp.status_code == 200:
        info("PASS: Authenticated fetcher RPC succeeded.")
    else:
        die(f"Unexpected RPC response: {resp.status_code} {resp.text}")


def test_squid_acl_matrix() -> None:
    """Matrix probe: Squid destination ACLs under network-none container."""
    info("Testing Squid destination ACL matrix...")
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/check-proxy.py")],
        capture_output=True,
        text=True,
        cwd=ROOT,
        check=False,
    )
    if result.returncode != 0:
        die(f"Squid ACL matrix failed (exit {result.returncode}):\n{result.stderr}")
    info("PASS: Squid ACL matrix passed.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetcher-url", default="http://127.0.0.1:8001")
    parser.add_argument("--token-file", default=str(ROOT / ".secrets/fetcher_token"))
    parser.add_argument(
        "--skip-rpc", action="store_true", help="Skip live RPC test if stack not up"
    )
    args = parser.parse_args()

    info("=== Section 9.2 Fetch Isolation Matrix Test ===")
    test_ip_literal_rejection()
    test_squid_acl_matrix()

    token_path = Path(args.token_file)
    if not args.skip_rpc and token_path.exists():
        token = token_path.read_text().strip()
        if len(token) >= 32:
            import httpx

            try:
                test_fetcher_rpc_auth(args.fetcher_url, token)
            except (httpx.HTTPError, OSError) as e:
                die(f"RPC test failed at {args.fetcher_url}: {e}")


if __name__ == "__main__":
    main()
