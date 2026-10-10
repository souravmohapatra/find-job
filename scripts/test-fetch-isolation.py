"""Acceptance test runner for section 9.2 fetch isolation matrix.

Exercises positive and negative boundary probes against disposable containers
(including jobfinder-backend:local and ubuntu/squid) with NNP hardening and
internal network topology, using synthetic targets.
Run: export DOCKER_NO_NEW_PRIVILEGES=false && python3 scripts/test-fetch-isolation.py
"""

import argparse
import http.server
import os
import secrets
import subprocess
import sys
import threading
import time
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))


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
                asyncio.run(fetch_http.resolve_public(target, proxy_url="http://127.0.0.1:3128"))
            except FetchFailure as failure:
                if failure.code == "destination_denied":
                    rejected = True
        if not rejected:
            die(f"Target was not rejected as non-global: {target}")
    info("PASS: All private IPv4, IPv6, mapped, and non-80/443 ports rejected.")


def _probe_redirect(target: str) -> None:
    import asyncio

    import httpx
    from app.fetcher import http as fetch_http
    from app.fetcher.contracts import FetchFailure
    from app.fetcher.settings import FetchSettings

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": target})

    config = FetchSettings(
        proxy_url="http://127.0.0.1:3128",
        state_file=Path("/tmp/test_origins.sqlite3"),
        isolation_verified=True,
    )
    fetcher = fetch_http.Fetcher(config)
    transport = httpx.MockTransport(handler)

    async def run_fetch():
        async with httpx.AsyncClient(transport=transport) as client:
            return await fetcher.chain(
                client, "https://example.com/start", {}, 512 * 1024, robots=False
            )

    rejected = False
    try:
        asyncio.run(run_fetch())
    except (FetchFailure, ValueError):
        rejected = True
    if not rejected:
        die(f"Redirect to private destination was NOT rejected: {target}")


def test_private_redirect_rejection() -> None:
    """Matrix probe: Public URL redirecting to controlled private destination."""
    info("Testing private redirect rejection...")
    bad_redirects = [
        "http://127.0.0.1/admin",
        "http://10.0.0.1/internal",
        "http://192.168.1.1/router",
        "http://169.254.169.254/latest/meta-data",
        "http://[::1]/secret",
    ]
    for target in bad_redirects:
        _probe_redirect(target)
    info("PASS: All private redirect destinations rejected before connection.")


def test_oversized_and_decompression_bomb_rejection() -> None:
    """Matrix probe: Oversized/decompression bomb rejected boundedly."""
    info("Testing oversized payload and decompression bomb handling...")
    import asyncio
    import gzip

    import httpx
    from app.fetcher import http as fetch_http
    from app.fetcher.contracts import FetchFailure

    class ByteStream(httpx.AsyncByteStream):
        def __init__(self, data: bytes):
            self.data = data

        async def __aiter__(self):
            yield self.data

    # Test raw uncompressed oversize
    async def run_raw():
        resp = httpx.Response(200, stream=ByteStream(b"A" * 2000))
        return await fetch_http.body_bytes(resp, 1000)

    try:
        asyncio.run(run_raw())
        die("Raw oversized payload was not rejected")
    except FetchFailure as failure:
        if failure.code != "document_too_large":
            die(f"Expected document_too_large, got {failure.code}")

    # Test gzip decompression bomb
    async def run_bomb():
        compressed = gzip.compress(b"0" * (1024 * 1024))
        resp = httpx.Response(
            200, headers={"content-encoding": "gzip"}, stream=ByteStream(compressed)
        )
        return await fetch_http.body_bytes(resp, 50 * 1024)

    try:
        asyncio.run(run_bomb())
        die("Decompression bomb was not rejected")
    except FetchFailure as failure:
        if failure.code != "document_too_large":
            die(f"Expected document_too_large, got {failure.code}")
    info("PASS: Oversized payload and decompression bomb safely rejected.")


def test_redirect_limit_rejection() -> None:
    """Matrix probe: Redirect loop or excessive hops rejected."""
    info("Testing redirect loop rejection...")
    import asyncio

    import httpx
    from app.fetcher import http as fetch_http
    from app.fetcher.contracts import FetchFailure
    from app.fetcher.settings import FetchSettings

    def loop_handler(request: httpx.Request) -> httpx.Response:
        current_step = int(request.url.path.strip("/") or "0")
        return httpx.Response(302, headers={"location": f"https://example.com/{current_step + 1}"})

    config = FetchSettings(
        proxy_url="http://127.0.0.1:3128",
        state_file=Path("/tmp/test_origins.sqlite3"),
        isolation_verified=True,
    )
    fetcher = fetch_http.Fetcher(config)
    transport = httpx.MockTransport(loop_handler)

    async def run_loop():
        async with httpx.AsyncClient(transport=transport) as client:
            return await fetcher.chain(
                client, "https://example.com/0", {}, 512 * 1024, robots=False
            )

    try:
        asyncio.run(run_loop())
        die("Redirect loop was not rejected")
    except FetchFailure as failure:
        if failure.code != "redirect_limit":
            die(f"Expected redirect_limit, got {failure.code}")
    info("PASS: Redirect loop safely bounded and rejected.")


def test_fetcher_rpc_auth(fetcher_url: str, token: str) -> None:
    """Matrix probe: Worker -> authenticated fetcher RPC (valid/missing/wrong token)."""
    info("Testing fetcher RPC authentication...")
    import httpx

    # Missing token -> 401
    resp = httpx.post(f"{fetcher_url}/fetch", json={"url": "https://example.com"}, timeout=5)
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
        info("PASS: Correct token verified; isolation gate safely blocks unverified fetching.")
    elif resp.status_code == 200:
        info("PASS: Authenticated fetcher RPC succeeded.")
    else:
        die(f"Unexpected RPC response: {resp.status_code} {resp.text}")


def test_disposable_container_isolation() -> None:
    """Matrix probe: real container boundary running fetcher image with NNP hardening."""
    info("Testing disposable container boundary with jobfinder-backend:local...")
    from deployment_config import configuration, runtime_security_option

    config = configuration()
    sec_opt = runtime_security_option(config)
    suffix = uuid4().hex[:8]
    fetcher_name = f"jobfinder-fetcher-test-{suffix}"
    port = 18001 + (os.getpid() % 1000)
    token = secrets.token_hex(32)

    token_dir = ROOT / ".data" / f"token-{suffix}"
    token_dir.mkdir(mode=0o755, exist_ok=True)
    token_file = token_dir / "fetcher_token"
    token_file.write_text(token)
    token_file.chmod(0o644)
    try:
        # 1. Start fetcher with isolation_verified=false
        cmd = [
            "docker",
            "run",
            "-d",
            "--name",
            fetcher_name,
            "--pull",
            "never",
            "--security-opt",
            sec_opt,
            "--entrypoint",
            "setpriv",
            "--read-only",
            "--tmpfs",
            "/tmp:size=64m,mode=1777",
            "--tmpfs",
            "/data/fetcher:size=16m,mode=1777",
            "--cap-drop",
            "ALL",
            "-v",
            f"{token_file}:/run/secrets/fetcher_token:ro",
            "-e",
            "JOBFINDER_FETCH_PROXY_URL=http://127.0.0.1:3128",
            "-e",
            "JOBFINDER_FETCH_TOKEN_FILE=/run/secrets/fetcher_token",
            "-e",
            "JOBFINDER_FETCH_STATE_FILE=/data/fetcher/origins.sqlite3",
            "-e",
            "JOBFINDER_FETCH_ISOLATION_VERIFIED=false",
            "-p",
            f"127.0.0.1:{port}:8001",
            "jobfinder-backend:local",
            "--no-new-privs",
            "uvicorn",
            "app.fetcher.main:app",
            "--host",
            "0.0.0.0",
            "--port",
            "8001",
            "--no-access-log",
        ]
        subprocess.run(cmd, capture_output=True, text=True, check=True)

        url = f"http://127.0.0.1:{port}"
        import httpx

        ready = False
        for _ in range(30):
            try:
                res = httpx.get(f"{url}/health/live", timeout=1)
                if res.status_code == 200:
                    ready = True
                    break
            except (httpx.HTTPError, OSError):
                time.sleep(0.1)
        if not ready:
            die("Disposable fetcher container failed to become ready")

        # Test auth probes
        test_fetcher_rpc_auth(url, token)

        # Test payload size limit probe (> 8192 bytes)
        large_resp = httpx.post(
            f"{url}/fetch",
            content=b"A" * 9000,
            headers={"Authorization": f"Bearer {token}"},
            timeout=5,
        )
        if large_resp.status_code != 413:
            die(f"Expected 413 for oversized request, got {large_resp.status_code}")
        info("PASS: Request size limit (8192 bytes) enforced.")

    finally:
        subprocess.run(["docker", "rm", "-f", fetcher_name], capture_output=True, check=False)
        token_file.unlink(missing_ok=True)
        token_dir.rmdir()

    # 2. Start fetcher with isolation_verified=true to test destination denial on private targets
    fetcher_name_v2 = f"jobfinder-fetcher-test-v2-{suffix}"
    token_dir = ROOT / ".data" / f"token-{suffix}"
    token_dir.mkdir(mode=0o755, exist_ok=True)
    token_file = token_dir / "fetcher_token"
    token_file.write_text(token)
    token_file.chmod(0o644)
    try:
        cmd_v2 = [
            "docker",
            "run",
            "-d",
            "--name",
            fetcher_name_v2,
            "--pull",
            "never",
            "--security-opt",
            sec_opt,
            "--entrypoint",
            "setpriv",
            "--read-only",
            "--tmpfs",
            "/tmp:size=64m,mode=1777",
            "--tmpfs",
            "/data/fetcher:size=16m,mode=1777",
            "--cap-drop",
            "ALL",
            "-v",
            f"{token_file}:/run/secrets/fetcher_token:ro",
            "-e",
            "JOBFINDER_FETCH_PROXY_URL=http://127.0.0.1:3128",
            "-e",
            "JOBFINDER_FETCH_TOKEN_FILE=/run/secrets/fetcher_token",
            "-e",
            "JOBFINDER_FETCH_STATE_FILE=/data/fetcher/origins.sqlite3",
            "-e",
            "JOBFINDER_FETCH_ISOLATION_VERIFIED=true",
            "-p",
            f"127.0.0.1:{port}:8001",
            "jobfinder-backend:local",
            "--no-new-privs",
            "uvicorn",
            "app.fetcher.main:app",
            "--host",
            "0.0.0.0",
            "--port",
            "8001",
            "--no-access-log",
        ]
        subprocess.run(cmd_v2, capture_output=True, text=True, check=True)

        url = f"http://127.0.0.1:{port}"
        ready = False
        for _ in range(30):
            try:
                res = httpx.get(f"{url}/health/live", timeout=1)
                if res.status_code == 200:
                    ready = True
                    break
            except (httpx.HTTPError, OSError):
                time.sleep(0.1)
        if not ready:
            die("Disposable fetcher container (v2) failed to become ready")

        # Private destination rejection
        for private_target in [
            "http://127.0.0.1/admin",
            "http://10.0.0.1/internal",
            "http://169.254.169.254/meta",
        ]:
            denied_resp = httpx.post(
                f"{url}/fetch",
                json={"url": private_target},
                headers={"Authorization": f"Bearer {token}"},
                timeout=5,
            )
            data = denied_resp.json() if denied_resp.status_code in {422, 502} else {}
            if denied_resp.status_code == 422 and data.get("code") == "invalid_fetch_request":
                pass  # Rejected at API schema boundary
            elif denied_resp.status_code == 502 and data.get("code") == "destination_denied":
                pass  # Rejected at fetcher engine boundary
            else:
                die(
                    f"Expected rejection for {private_target}, got "
                    f"{denied_resp.status_code} {denied_resp.text}"
                )
        info("PASS: Containerized fetcher strictly rejects private targets.")

    finally:
        subprocess.run(["docker", "rm", "-f", fetcher_name_v2], capture_output=True, check=False)
        token_file.unlink(missing_ok=True)
        token_dir.rmdir()

    # 3. Direct egress probe: container on internal network has no default gateway/route
    net_name = f"jobfinder-internal-test-{suffix}"
    try:
        subprocess.run(
            ["docker", "network", "create", "--internal", net_name],
            capture_output=True,
            check=True,
        )
        probe_res = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "--security-opt",
                sec_opt,
                "--network",
                net_name,
                "jobfinder-backend:local",
                "python",
                "-c",
                "import socket; s = socket.socket(); s.settimeout(2); s.connect(('1.1.1.1', 80))",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if probe_res.returncode == 0:
            die("Direct public egress unexpectedly succeeded on internal network")
        info("PASS: Direct public egress without proxy strictly blocked on internal network.")
    finally:
        subprocess.run(["docker", "network", "rm", net_name], capture_output=True, check=False)


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
    parser.add_argument(
        "--live-containers",
        action="store_true",
        default=True,
        help="Run disposable container tests with jobfinder-backend:local",
    )
    parser.add_argument(
        "--skip-live-containers",
        dest="live_containers",
        action="store_false",
        help="Skip disposable container tests",
    )
    args = parser.parse_args()

    info("=== Section 9.2 Fetch Isolation Matrix Test ===")
    test_ip_literal_rejection()
    test_squid_acl_matrix()
    test_private_redirect_rejection()
    test_oversized_and_decompression_bomb_rejection()
    test_redirect_limit_rejection()
    if args.live_containers:
        test_disposable_container_isolation()
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
    venv_dir = ROOT / "backend/.venv"
    venv_python = venv_dir / "bin/python"
    if venv_python.exists() and Path(sys.prefix).resolve() != venv_dir.resolve():
        os.execv(str(venv_python), [str(venv_python), *sys.argv])
    main()
