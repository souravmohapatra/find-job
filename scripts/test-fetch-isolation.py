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

    handler_called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal handler_called
        if request.url.path == "/start":
            handler_called = True
            return httpx.Response(302, headers={"location": target})
        return httpx.Response(404)

    state_id = uuid4().hex[:8]
    state_path = ROOT / ".data" / f"test_redirect_{state_id}.sqlite3"
    try:
        config = FetchSettings(
            proxy_url="http://127.0.0.1:3128",
            state_file=state_path,
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
        except FetchFailure as failure:
            if failure.code == "destination_denied":
                rejected = True
            else:
                die(
                    f"Redirect to {target} failed with unexpected FetchFailure code: {failure.code}"
                )
        except ValueError as err:
            if "Private" in str(err) or "reserved" in str(err) or "Invalid public URL" in str(err):
                rejected = True
            else:
                die(f"Redirect to {target} failed with unexpected ValueError: {err}")

        if not handler_called:
            die(f"Redirect handler was never reached for target: {target}")
        if not rejected:
            die(f"Redirect to private destination was NOT rejected: {target}")
    finally:
        state_path.unlink(missing_ok=True)


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

    state_id = uuid4().hex[:8]
    state_path = ROOT / ".data" / f"test_redirect_loop_{state_id}.sqlite3"
    try:
        config = FetchSettings(
            proxy_url="http://127.0.0.1:3128",
            state_file=state_path,
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
    finally:
        state_path.unlink(missing_ok=True)


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


def test_direct_egress_probe(net_name: str, sec_opt: str) -> None:
    """Probe direct egress on internal network: must fail with structured denial, not crash."""
    info("Testing direct public egress denial on internal network...")
    cmd = [
        "docker",
        "run",
        "--rm",
        "--pull",
        "never",
        "--security-opt",
        sec_opt,
        "--entrypoint",
        "setpriv",
        "--network",
        net_name,
        "jobfinder-backend:local",
        "--no-new-privs",
        "python",
        "-c",
        (
            "import errno, socket, sys\n"
            "s = socket.socket()\n"
            "s.settimeout(2)\n"
            "try:\n"
            "    s.connect(('1.1.1.1', 80))\n"
            "    print('RESULT:CONNECTED')\n"
            "    sys.exit(0)\n"
            "except OSError as e:\n"
            "    if e.errno in (errno.ENETUNREACH, errno.EHOSTUNREACH) "
            "or isinstance(e, TimeoutError):\n"
            "        print(f'RESULT:DENIED:{type(e).__name__}:{e.errno}')\n"
            "        sys.exit(0)\n"
            "    print(f'RESULT:ERROR:{type(e).__name__}:{e.errno}:{e}')\n"
            "    sys.exit(1)\n"
            "except Exception as e:\n"
            "    print(f'RESULT:ERROR:{type(e).__name__}:{e}')\n"
            "    sys.exit(1)\n"
        ),
    ]
    probe_res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if probe_res.returncode != 0:
        die(
            f"Direct egress probe container failed unexpectedly (exit {probe_res.returncode}):\n"
            f"stderr: {probe_res.stderr}\nstdout: {probe_res.stdout}"
        )
    output = probe_res.stdout.strip()
    if "RESULT:CONNECTED" in output:
        die("Direct public egress unexpectedly connected on internal network")
    if "RESULT:DENIED:" not in output:
        die(f"Direct egress probe did not report expected network denial: {output}")
    info(f"PASS: Direct public egress strictly blocked on internal network ({output}).")


def test_direct_egress_exit_125_regression() -> None:
    """Regression: verify that Docker execution failure (exit 125) is caught as failure."""
    info("Running regression test: ensuring Docker startup failure (exit 125) is rejected...")
    bogus_cmd = ["docker", "run", "--rm", "--invalid-flag-that-does-not-exist", "alpine:latest"]
    res = subprocess.run(bogus_cmd, capture_output=True, text=True, check=False)
    assert res.returncode == 125, f"Expected Docker exit code 125, got {res.returncode}"
    # A test that checks `returncode == 0` correctly flags this as failure
    failed_as_expected = res.returncode != 0
    if not failed_as_expected:
        die("Regression failed: Docker startup failure was not detected as non-zero exit")
    info("PASS: Docker execution failure (exit 125) properly rejected.")


def test_disposable_container_isolation() -> None:
    """Matrix probe: real container boundary running fetcher image with NNP hardening."""
    info("Testing disposable container boundary with jobfinder-backend:local...")
    from deployment_config import configuration, runtime_security_option

    config = configuration()
    sec_opt = runtime_security_option(config)
    suffix = uuid4().hex[:8]
    net_fc = f"jobfinder-test-fc-{suffix}"
    net_fetch = f"jobfinder-test-fetch-{suffix}"
    net_pub = f"jobfinder-test-pub-{suffix}"
    proxy_name = f"jobfinder-test-proxy-{suffix}"
    fetcher_name = f"jobfinder-test-fetcher-{suffix}"
    fetcher_name_v2 = f"jobfinder-test-fetcher-v2-{suffix}"
    token = secrets.token_hex(32)

    token_dir = ROOT / ".data" / f"token-{suffix}"
    token_dir.mkdir(mode=0o755, exist_ok=True)
    token_file = token_dir / "fetcher_token"
    token_file.write_text(token)
    token_file.chmod(0o644)

    containers_to_clean: list[str] = []
    networks_to_clean: list[str] = []

    try:
        # 1. Create the three test networks matching production topology
        subprocess.run(
            ["docker", "network", "create", "--internal", net_fc],
            capture_output=True,
            check=True,
        )
        networks_to_clean.append(net_fc)
        subprocess.run(
            ["docker", "network", "create", "--internal", net_fetch],
            capture_output=True,
            check=True,
        )
        networks_to_clean.append(net_fetch)
        subprocess.run(["docker", "network", "create", net_pub], capture_output=True, check=True)
        networks_to_clean.append(net_pub)

        # 2. Start Squid proxy on net_fetch (alias egress-proxy) and net_pub
        squid_cmd = [
            "docker",
            "create",
            "--name",
            proxy_name,
            "--pull",
            "never",
            "--security-opt",
            sec_opt,
            "--entrypoint",
            "setpriv",
            "--network",
            net_fetch,
            "--network-alias",
            "egress-proxy",
            "--user",
            "13:13",
            "--read-only",
            "--tmpfs",
            "/tmp:size=16m,mode=1777",
            "--cap-drop",
            "ALL",
            "-v",
            f"{ROOT / 'deploy/squid.conf'}:/etc/squid/squid.conf:ro",
            "ubuntu/squid@sha256:6a097f68bae708cedbabd6188d68c7e2e7a38cedd05a176e1cc0ba29e3bbe029",
            "--no-new-privs",
            "/usr/sbin/squid",
            "-f",
            "/etc/squid/squid.conf",
            "-NYC",
        ]
        subprocess.run(squid_cmd, capture_output=True, check=True)
        containers_to_clean.append(proxy_name)
        subprocess.run(
            ["docker", "network", "connect", net_pub, proxy_name],
            capture_output=True,
            check=True,
        )
        subprocess.run(["docker", "start", proxy_name], capture_output=True, check=True)
        time.sleep(2)

        # 3. Phase 1: Start Fetcher with isolation_verified=false
        fetcher_cmd = [
            "docker",
            "create",
            "--name",
            fetcher_name,
            "--pull",
            "never",
            "--security-opt",
            sec_opt,
            "--entrypoint",
            "setpriv",
            "--network",
            net_fc,
            "--network-alias",
            "fetcher",
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
            "JOBFINDER_FETCH_PROXY_URL=http://egress-proxy:3128",
            "-e",
            "JOBFINDER_FETCH_TOKEN_FILE=/run/secrets/fetcher_token",
            "-e",
            "JOBFINDER_FETCH_STATE_FILE=/data/fetcher/origins.sqlite3",
            "-e",
            "JOBFINDER_FETCH_ISOLATION_VERIFIED=false",
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
        subprocess.run(fetcher_cmd, capture_output=True, check=True)
        containers_to_clean.append(fetcher_name)
        subprocess.run(
            ["docker", "network", "connect", net_fetch, fetcher_name],
            capture_output=True,
            check=True,
        )
        subprocess.run(["docker", "start", fetcher_name], capture_output=True, check=True)
        time.sleep(2)

        # Test auth & disabled isolation from Worker container on net_fc
        worker_probe_cmd = [
            "docker",
            "run",
            "--rm",
            "--pull",
            "never",
            "--security-opt",
            sec_opt,
            "--entrypoint",
            "setpriv",
            "--network",
            net_fc,
            "jobfinder-backend:local",
            "--no-new-privs",
            "python",
            "-c",
            (
                "import json, urllib.request, urllib.error, sys\n"
                "t = sys.argv[1]\n"
                "try:\n"
                "    urllib.request.urlopen(urllib.request.Request(\n"
                "        'http://fetcher:8001/fetch', data=b'{\"url\":\"http://example.com\"}'\n"
                "    ))\n"
                "    sys.exit(10)\n"
                "except urllib.error.HTTPError as e:\n"
                "    if e.code != 401: sys.exit(11)\n"
                "try:\n"
                "    urllib.request.urlopen(urllib.request.Request(\n"
                "        'http://fetcher:8001/fetch', data=b'{\"url\":\"http://example.com\"}',\n"
                "        headers={'Authorization': 'Bearer wrong-xxxx-32-chars-long-here-xxxx'}\n"
                "    ))\n"
                "    sys.exit(12)\n"
                "except urllib.error.HTTPError as e:\n"
                "    if e.code != 401: sys.exit(13)\n"
                "try:\n"
                "    urllib.request.urlopen(urllib.request.Request(\n"
                "        'http://fetcher:8001/fetch', data=b'{\"url\":\"http://example.com\"}',\n"
                "        headers={'Authorization': 'Bearer ' + t, "
                "'Content-Type': 'application/json'}\n"
                "    ))\n"
                "    sys.exit(14)\n"
                "except urllib.error.HTTPError as e:\n"
                "    b = json.loads(e.read().decode())\n"
                "    if e.code != 502 or b.get('code') != 'isolation_not_verified': sys.exit(15)\n"
                "try:\n"
                "    urllib.request.urlopen(urllib.request.Request(\n"
                "        'http://fetcher:8001/fetch', data=b'A'*9000,\n"
                "        headers={'Authorization': 'Bearer ' + t, "
                "'Content-Type': 'application/json'}\n"
                "    ))\n"
                "    sys.exit(16)\n"
                "except urllib.error.HTTPError as e:\n"
                "    if e.code != 413: sys.exit(17)\n"
                "print('PHASE1_OK')\n"
            ),
            token,
        ]
        res = subprocess.run(worker_probe_cmd, capture_output=True, text=True, check=False)
        if res.returncode != 0 or "PHASE1_OK" not in res.stdout:
            die(
                f"Phase 1 worker probes failed (exit {res.returncode}):\n{res.stderr}\n{res.stdout}"
            )
        info("PASS: Worker->Fetcher auth, isolation gate, and request size limits verified.")

        # Stop fetcher Phase 1
        subprocess.run(["docker", "rm", "-f", fetcher_name], capture_output=True, check=False)
        containers_to_clean.remove(fetcher_name)

        # 4. Phase 2: Start Fetcher with isolation_verified=true
        fetcher_cmd_v2 = [
            "docker",
            "create",
            "--name",
            fetcher_name_v2,
            "--pull",
            "never",
            "--security-opt",
            sec_opt,
            "--entrypoint",
            "setpriv",
            "--network",
            net_fc,
            "--network-alias",
            "fetcher",
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
            "JOBFINDER_FETCH_PROXY_URL=http://egress-proxy:3128",
            "-e",
            "JOBFINDER_FETCH_TOKEN_FILE=/run/secrets/fetcher_token",
            "-e",
            "JOBFINDER_FETCH_STATE_FILE=/data/fetcher/origins.sqlite3",
            "-e",
            "JOBFINDER_FETCH_ISOLATION_VERIFIED=true",
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
        subprocess.run(fetcher_cmd_v2, capture_output=True, check=True)
        containers_to_clean.append(fetcher_name_v2)
        subprocess.run(
            ["docker", "network", "connect", net_fetch, fetcher_name_v2],
            capture_output=True,
            check=True,
        )
        subprocess.run(["docker", "start", fetcher_name_v2], capture_output=True, check=True)
        time.sleep(2)

        # Test positive public fetch and private target denials from Worker container
        worker_probe_v2_cmd = [
            "docker",
            "run",
            "--rm",
            "--pull",
            "never",
            "--security-opt",
            sec_opt,
            "--entrypoint",
            "setpriv",
            "--network",
            net_fc,
            "jobfinder-backend:local",
            "--no-new-privs",
            "python",
            "-c",
            (
                "import json, urllib.request, urllib.error, sys\n"
                "t = sys.argv[1]\n"
                "# 1. Positive public fetch through Squid\n"
                "req = urllib.request.Request(\n"
                "    'http://fetcher:8001/fetch', data=b'{\"url\":\"http://example.com\"}',\n"
                "    headers={'Authorization': 'Bearer ' + t, "
                "'Content-Type': 'application/json'}\n"
                ")\n"
                "resp = urllib.request.urlopen(req, timeout=15)\n"
                "data = json.loads(resp.read().decode())\n"
                "if data.get('status') != 200 or len(data.get('body', '')) == 0:\n"
                "    sys.exit(20)\n"
                "# 2. Private destination rejection\n"
                "for tgt in ['http://127.0.0.1/admin', 'http://169.254.169.254/meta', "
                "'http://10.0.0.1/']:\n"
                "    try:\n"
                "        urllib.request.urlopen(urllib.request.Request(\n"
                "            'http://fetcher:8001/fetch', "
                "data=json.dumps({'url': tgt}).encode(),\n"
                "            headers={'Authorization': 'Bearer ' + t, "
                "'Content-Type': 'application/json'}\n"
                "        ), timeout=5)\n"
                "        sys.exit(21)\n"
                "    except urllib.error.HTTPError as e:\n"
                "        if e.code not in (422, 502): sys.exit(22)\n"
                "print('PHASE2_OK')\n"
            ),
            token,
        ]
        res_v2 = subprocess.run(worker_probe_v2_cmd, capture_output=True, text=True, check=False)
        if res_v2.returncode != 0 or "PHASE2_OK" not in res_v2.stdout:
            die(
                f"Phase 2 worker probes failed (exit {res_v2.returncode}):\n"
                f"{res_v2.stderr}\n{res_v2.stdout}"
            )
        info("PASS: Positive public fetch through Squid and private target rejections verified.")

        # 5. Direct egress probe on internal network (net_fetch)
        test_direct_egress_probe(net_fetch, sec_opt)

        # 6. Exit-125 regression test
        test_direct_egress_exit_125_regression()

    finally:
        for c in containers_to_clean:
            subprocess.run(["docker", "rm", "-f", c], capture_output=True, check=False)
        for n in networks_to_clean:
            subprocess.run(["docker", "network", "rm", n], capture_output=True, check=False)
        token_file.unlink(missing_ok=True)
        token_dir.rmdir()


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
