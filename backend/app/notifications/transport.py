"""Bounded ntfy publishing to a deployment-configured origin; never follows redirects."""

import json
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any, Literal
from urllib.parse import urlsplit

import httpx
from app.config import get_settings
from app.notifications.contracts import DigestSnapshot


@dataclass(frozen=True)
class Outcome:
    state: Literal["sent", "failed", "unknown"]
    code: str | None = None
    remote_id: str | None = None
    retryable: bool = False
    retry_after: int = 60


def target() -> dict[str, Any]:
    config = get_settings()
    return {
        "mode": config.notification_mode,
        "server": config.ntfy_url,
        "topic": config.ntfy_topic,
        "app_url": config.notification_app_url,
    }


def origin(value: str) -> bool:
    try:
        parts = urlsplit(value)
        return bool(
            parts.scheme in {"http", "https"}
            and parts.hostname
            and not parts.username
            and not parts.password
            and not parts.query
            and not parts.fragment
            and parts.path in {"", "/"}
            and parts.port != 0
            and value.isascii()
            and not any(character.isspace() for character in value)
        )
    except ValueError:
        return False


def message(snapshot: dict[str, Any], mode: str) -> str:
    data = DigestSnapshot.model_validate(snapshot)
    counts = data.counts
    lines = [
        f"{counts.new} new shortlisted roles.",
        f"Baseline: {counts.baseline}. Newly suitable after reassessment: {counts.reassessment}.",
    ]
    if mode == "mock":
        lines.insert(0, "Synthetic assessment results (development mode).")
    if not data.matching_available:
        lines.append("Matching is unavailable; review your profile and model settings.")
    lines.append(
        f"Checks needing attention: {data.source_errors}; "
        f"assessment errors: {data.assessment_errors}; "
        f"unresolved companies: {data.unresolved_companies}; "
        f"pending tasks: {data.pending_operations}."
    )
    for company in data.companies.values():
        lines.append(f"{company.label}: {company.count}")
    for entry in data.examples:
        lines.append(f"{entry.company}: {entry.title}")
    # ntfy's default message limit is 4 KiB. Keep UTF-8 complete and leave room
    # for the closing link instruction; the digest retains every omitted item.
    body = "\n".join(lines).encode("utf-8")
    if len(body) > 3300:
        body = body[:3300].decode("utf-8", errors="ignore").encode("utf-8") + b"\n..."
    return body.decode("utf-8") + "\nOpen the full shortlist for all results."


def retry_delay(value: str) -> int:
    # A delay beyond the 30-minute delivery window stops retries; never shorten
    # a long server cooldown into a retry that would violate Retry-After.
    if re.fullmatch(r"[0-9]+", value):
        digits = value.lstrip("0") or "0"
        # Beyond the representable calendar means no automatic early retry.
        return 315_576_000_000 if len(digits) > 12 else min(int(digits), 315_576_000_000)
    try:
        parsed = parsedate_to_datetime(value)
        return max(0, int((parsed - datetime.now(UTC)).total_seconds()) + 1)
    except (ValueError, TypeError, OverflowError):
        return 60


def publish(destination: dict[str, Any], body: str) -> Outcome:
    if destination.get("mode") != "live" or get_settings().notification_mode != "live":
        return Outcome("failed", "notification_mock_mode")
    if destination != target():
        return Outcome("failed", "notification_destination_changed")
    if not body or len(body.encode("utf-8")) > 4096:
        return Outcome("failed", "notification_message_limit")
    server, app_url, topic = (destination.get(key) for key in ("server", "app_url", "topic"))
    if (
        not isinstance(server, str)
        or not origin(server)
        or not isinstance(app_url, str)
        or not origin(app_url)
        or not isinstance(topic, str)
        or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", topic)
    ):
        return Outcome("failed", "notification_configuration_required")
    try:
        token = get_settings().ntfy_token_file.read_text().strip()
    except OSError:
        return Outcome("failed", "notification_token_required")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,1024}", token):
        return Outcome("failed", "notification_token_invalid")
    try:
        started = time.monotonic()
        with httpx.Client(
            trust_env=False, follow_redirects=False, timeout=httpx.Timeout(10, connect=5)
        ) as client:
            with client.stream(
                "POST",
                server.rstrip("/") + "/" + topic,
                content=body.encode("utf-8"),
                headers={
                    "Authorization": "Bearer " + token,
                    "Title": "Job Finder daily summary",
                    "Click": app_url.rstrip("/") + "/jobs",
                    "Content-Type": "text/plain; charset=utf-8",
                },
            ) as response:
                if response.status_code == 429:
                    retry = response.headers.get("retry-after", "60")
                    return Outcome(
                        "failed",
                        "ntfy_rate_limited",
                        retryable=True,
                        retry_after=retry_delay(retry),
                    )
                if 300 <= response.status_code < 500:
                    return Outcome("failed", "ntfy_rejected")
                if response.status_code != 200:
                    return Outcome("unknown", "ntfy_unconfirmed_response")
                raw = bytearray()
                for chunk in response.iter_bytes():
                    raw.extend(chunk)
                    if len(raw) > 32768 or time.monotonic() - started > 20:
                        return Outcome("unknown", "ntfy_response_limit")
                try:
                    result = json.loads(raw)
                except (ValueError, UnicodeDecodeError):
                    return Outcome("unknown", "ntfy_invalid_receipt")
                if (
                    not isinstance(result, dict)
                    or result.get("event") != "message"
                    or result.get("topic") != topic
                    or not isinstance(result.get("id"), str)
                    or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", result["id"])
                ):
                    return Outcome("unknown", "ntfy_invalid_receipt")
                return Outcome("sent", remote_id=result["id"])
    except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout):
        return Outcome("failed", "ntfy_connect_failed", retryable=True)
    except httpx.HTTPError:
        return Outcome("unknown", "ntfy_delivery_unknown")
