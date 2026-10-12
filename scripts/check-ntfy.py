"""Validate private ntfy connectivity and publisher token permissions.

Validates that:
1. The ntfy server on 127.0.0.1:8093 is healthy.
2. Dedicated token (.secrets/ntfy_publisher_token) exists with valid format.
3. Anonymous publish and read to the jobfinder topic are rejected (403/401).
4. Publisher token is write-only: message polling/reading is rejected (403).
5. Publisher token is topic-isolated: publishing to other topics is rejected (403).
6. Publisher token is authorized on topic (OPTIONS returns 200).
7. No test notification is sent without explicit owner confirmation.
"""

import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOKEN_FILE = ROOT / ".secrets/ntfy_publisher_token"


def validate_ntfy(server_url: str = "http://127.0.0.1:8093", topic: str = "jobfinder") -> int:
    if not TOKEN_FILE.exists():
        print(f"FAILED: Publisher token file {TOKEN_FILE} does not exist", file=sys.stderr)
        return 1
    token = TOKEN_FILE.read_text().strip()
    if not re.fullmatch(r"tk_[A-Za-z0-9]+", token):
        print(f"FAILED: Publisher token in {TOKEN_FILE} has invalid format", file=sys.stderr)
        return 1

    # 1. Health check
    try:
        resp = urllib.request.urlopen(f"{server_url}/v1/health", timeout=5)
        data = json.loads(resp.read().decode())
        if not data.get("healthy"):
            print(f"FAILED: ntfy server at {server_url} is not healthy: {data}", file=sys.stderr)
            return 1
    except Exception as e:
        print(f"FAILED: Could not connect to ntfy server at {server_url}: {e}", file=sys.stderr)
        return 1

    # 2. Anonymous access denied (403/401)
    for path, method in [
        (f"{server_url}/{topic}", "POST"),
        (f"{server_url}/{topic}/json?poll=1", "GET"),
    ]:
        req = urllib.request.Request(path, method=method)
        try:
            urllib.request.urlopen(req, timeout=5)
            print(f"FAILED: Anonymous access to {path} was not denied", file=sys.stderr)
            return 1
        except urllib.error.HTTPError as e:
            if e.code not in (401, 403):
                print(
                    f"FAILED: Anonymous access to {path} returned status {e.code}",
                    file=sys.stderr,
                )
                return 1

    # 3. Publisher token write-only check: reading topic must be denied (403)
    read_req = urllib.request.Request(
        f"{server_url}/{topic}/json?poll=1",
        headers={"Authorization": f"Bearer {token}"},
        method="GET",
    )
    try:
        urllib.request.urlopen(read_req, timeout=5)
        print(
            "FAILED: Publisher token was able to read messages (must be write-only)",
            file=sys.stderr,
        )
        return 1
    except urllib.error.HTTPError as e:
        if e.code != 403:
            print(f"FAILED: Publisher token read returned {e.code}, expected 403", file=sys.stderr)
            return 1

    # 4. Publisher token topic isolation: writing to unrelated topic must be denied (403)
    other_req = urllib.request.Request(
        f"{server_url}/unrelated-topic-isolation-test",
        headers={"Authorization": f"Bearer {token}"},
        data=b"",
        method="POST",
    )
    try:
        urllib.request.urlopen(other_req, timeout=5)
        print("FAILED: Publisher token was able to access unrelated topic", file=sys.stderr)
        return 1
    except urllib.error.HTTPError as e:
        if e.code != 403:
            print(
                f"FAILED: Publisher token other-topic returned {e.code}, expected 403",
                file=sys.stderr,
            )
            return 1

    # 5. Publisher token authorized for topic: OPTIONS request returns 200
    options_req = urllib.request.Request(
        f"{server_url}/{topic}",
        headers={"Authorization": f"Bearer {token}"},
        method="OPTIONS",
    )
    try:
        opt_resp = urllib.request.urlopen(options_req, timeout=5)
        if opt_resp.status != 200:
            print(
                f"FAILED: Publisher token OPTIONS returned {opt_resp.status}, expected 200",
                file=sys.stderr,
            )
            return 1
    except Exception as e:
        print(f"FAILED: Publisher token OPTIONS request failed: {e}", file=sys.stderr)
        return 1

    print(f"ntfy server healthy at {server_url}.")
    print(f"Dedicated publish-only credential verified for topic '{topic}'.")
    print(
        "Permissions validated: write-only enforced, topic isolation enforced, "
        "anonymous access denied."
    )
    print("No test notification was sent (requires owner confirmation).")
    return 0


def main() -> None:
    sys.exit(validate_ntfy())


if __name__ == "__main__":
    main()
