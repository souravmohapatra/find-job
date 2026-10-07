"""Fixed Brave Web Search endpoint with conservative durable request accounting.

Only company queries enter this module. Responses are unverified discovery leads.
https://api-dashboard.search.brave.com/app/documentation/web-search/get-started
"""

import json
import math
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Any
from uuid import UUID

import httpx
from app.collection.ats import plain
from app.collection.contracts import public_link
from app.collection.models import SearchRequest, SearchState
from app.config import get_settings
from app.db import get_engine
from app.profile_models import now
from app.services.operations import OperationError
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

ENDPOINT = "https://api.search.brave.com/res/v1/web/search"
MAX_RESPONSE = 2 * 1024 * 1024


def client() -> httpx.Client:
    return httpx.Client(timeout=30, trust_env=False, follow_redirects=False)


def decode(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict) or not isinstance(payload.get("web"), dict):
        raise ValueError("Missing web search results.")
    rows = payload["web"].get("results")
    if not isinstance(rows, list) or len(rows) > 20:
        raise ValueError("Invalid search results.")
    results = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("title"), str):
            continue
        try:
            url = public_link(row["url"])
        except (KeyError, ValueError, TypeError, AttributeError):
            continue
        if url in seen:
            continue
        seen.add(url)
        # Snippets never become job descriptions or verified identity evidence.
        results.append(
            {
                "url": url,
                "title": plain(row["title"])[:1000],
                "employer": None,
                "source_url": url,
                "evidence_path": "brave.web.results",
                "status": "needs_identity_review",
            }
        )
    return results


def retry_after(value: str | None) -> int:
    if not value:
        return 60
    try:
        if value.isdecimal():
            return min(int(value), 10**12)
        instant = parsedate_to_datetime(value)
        return min(max(1, math.ceil((instant.astimezone(UTC) - now()).total_seconds())), 10**12)
    except (ValueError, OverflowError, TypeError):
        return 60


def search(run_id: UUID, slot: int, query: str) -> list[dict[str, Any]]:
    settings = get_settings()
    if settings.search_mode != "live":
        raise OperationError("search_mock_mode", "Web search is in mock mode.", blocked=True)
    if not 0 <= slot <= 2 or not query.strip() or len(query) > 1000:
        raise OperationError("search_input", "The search request is invalid.")
    try:
        token = settings.brave_key_file.read_text().strip()
    except OSError:
        token = ""
    if not token or any(ord(char) < 33 for char in token):
        raise OperationError(
            "search_unconfigured", "Configure the Brave Search credential.", blocked=True
        )
    with Session(get_engine()) as db, db.begin():
        db.execute(text("SELECT pg_advisory_xact_lock(1012003)"))
        existing = db.scalar(
            select(SearchRequest).where(SearchRequest.run_id == run_id, SearchRequest.slot == slot)
        )
        if existing:
            if existing.query != query:
                raise OperationError("search_conflict", "This search slot has different input.")
            if existing.state == "succeeded":
                return existing.results
            raise OperationError(
                existing.error_code or "search_outcome_unknown",
                "The previous search outcome is unavailable; it will not be repeated.",
                blocked=True,
            )
        clock = now()
        day_start = clock.replace(hour=0, minute=0, second=0, microsecond=0)
        month_start = day_start.replace(day=1)
        daily = (
            db.scalar(
                select(func.count())
                .select_from(SearchRequest)
                .where(SearchRequest.requested_at >= day_start)
            )
            or 0
        )
        monthly = (
            db.scalar(
                select(func.count())
                .select_from(SearchRequest)
                .where(SearchRequest.requested_at >= month_start)
            )
            or 0
        )
        if daily >= settings.search_daily_limit or monthly >= settings.search_monthly_limit:
            raise OperationError(
                "search_budget", "The configured search request budget is exhausted.", blocked=True
            )
        state = db.get(SearchState, 1)
        if state is None:
            state = SearchState(id=1, next_allowed_at=clock)
            db.add(state)
        if state.next_allowed_at > clock:
            raise OperationError(
                "search_cooldown",
                "Search is waiting for its next request slot.",
                retryable=True,
                retry_after=min(
                    math.ceil((state.next_allowed_at - clock).total_seconds()), 30 * 86400
                ),
            )
        state.next_allowed_at = clock + timedelta(seconds=1)
        reservation = SearchRequest(run_id=run_id, slot=slot, query=query)
        db.add(reservation)
        db.flush()
        identifier = reservation.id
    results: list[dict[str, Any]] = []
    error: str | None = None
    cooldown = 0
    try:
        with (
            client() as http,
            http.stream(
                "GET",
                ENDPOINT,
                params={"q": query, "count": 20},
                headers={"X-Subscription-Token": token, "Accept": "application/json"},
            ) as response,
        ):
            if response.status_code == 429:
                cooldown = retry_after(response.headers.get("Retry-After"))
                error = "search_rate_limited"
            elif response.status_code != 200:
                error = "search_provider_error"
            else:
                body = bytearray()
                for chunk in response.iter_bytes(chunk_size=65536):
                    body.extend(chunk)
                    if len(body) > MAX_RESPONSE:
                        raise ValueError("Search response too large.")
                results = decode(json.loads(body))
    except httpx.HTTPError:
        error = "search_outcome_unknown"
    except (ValueError, TypeError, RecursionError):
        error = "search_invalid_response"
    with Session(get_engine()) as db, db.begin():
        db.execute(text("SELECT pg_advisory_xact_lock(1012003)"))
        saved = db.get(SearchRequest, identifier, with_for_update=True)
        assert saved is not None
        saved.state = "failed" if error else "succeeded"
        saved.error_code = error
        saved.results = results
        if cooldown:
            state = db.get(SearchState, 1)
            assert state is not None
            # datetime cannot represent arbitrary provider holds; cap at its maximum.
            horizon = datetime.max.replace(tzinfo=UTC) - timedelta(days=1)
            deadline = now() + timedelta(
                seconds=min(cooldown, int((horizon - now()).total_seconds()))
            )
            state.next_allowed_at = max(state.next_allowed_at, deadline)
    if error:
        raise OperationError(
            error, "Search could not return usable discovery candidates.", blocked=True
        )
    return results
