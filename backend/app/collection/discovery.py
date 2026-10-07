"""One fetched page per durable discovery step; no profile data or direct HTTP."""

import re
from datetime import timedelta
from typing import Any
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

from app.collection.ats import decode_page, request_url
from app.collection.contracts import Adapter, public_link
from app.collection.generic import parse_page
from app.collection.inventory import key
from app.collection.models import Company, DiscoveryRun, Source
from app.collection.transport import fetch_document, fetch_json
from app.db import get_engine
from app.fetcher.contracts import FetchRequest
from app.profile_models import Operation, now
from app.services.operations import OperationError, create_operation
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

MAX_PAGES = 20


class Target(BaseModel):
    url: str
    depth: int = 0
    linked_from: str | None = None
    adapter: Adapter | None = None
    board: str | None = None
    region: str = "global"
    query: str | None = None
    search_slot: int = 0


class DiscoveryResult(BaseModel):
    links: list[Target] = Field(default_factory=list)
    verified: Target | None = None
    candidates: list[dict[str, Any]] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)


def target(url: str, *, depth: int = 0, linked_from: str | None = None) -> Target:
    url = public_link(url)
    parts = urlsplit(url)
    path = parts.path.strip("/").split("/")
    board = path[0] if path else ""
    adapter: Adapter | None = None
    region = "global"
    if parts.hostname == "boards.greenhouse.io" and parts.path == "/embed/job_board":
        adapter = "greenhouse"
        board = parse_qs(parts.query).get("for", [""])[0]
    elif parts.hostname in {"boards.greenhouse.io", "job-boards.greenhouse.io"}:
        adapter = "greenhouse"
    elif parts.hostname in {"jobs.lever.co", "jobs.eu.lever.co"}:
        adapter = "lever"
        region = "eu" if parts.hostname == "jobs.eu.lever.co" else "global"
    elif parts.hostname == "jobs.ashbyhq.com":
        adapter = "ashby"
    if adapter and re.fullmatch(r"[A-Za-z0-9_-]{1,200}", board):
        return Target(
            url=request_url(adapter, board, region=region),
            adapter=adapter,
            board=board,
            region=region,
            depth=depth,
            linked_from=linked_from,
        )
    return Target(url=url, depth=depth, linked_from=linked_from)


def search_target(company_name: str) -> Target:
    name = " ".join(re.sub(r"[^\w\s.-]", " ", company_name).split())
    return Target(url="", query=f'"{name}" careers jobs', search_slot=0)


def same_site(url: str, website: str) -> bool:
    # No guessed registrable-domain equivalence: trust only the supplied host and its children.
    root = (urlsplit(website).hostname or "").removeprefix("www.")
    host = urlsplit(url).hostname or ""
    return host == root or host.endswith("." + root)


def step_operation(db: Session, run: DiscoveryRun) -> Operation:
    return create_operation(
        db,
        "discovery_step",
        f"{run.id}:{run.cursor}",
        {"run_id": str(run.id), "cursor": run.cursor},
    )


def begin(db: Session, company: Company) -> Operation | None:
    """Caller locks company; manual/scheduled work joins an existing fresh epoch."""
    if company.paused:
        return None
    active = db.scalar(
        select(DiscoveryRun)
        .where(DiscoveryRun.company_id == company.id, DiscoveryRun.state == "running")
        .with_for_update()
    )
    if active:
        if active.company_revision == company.revision and active.started_at > now() - timedelta(
            hours=24
        ):
            operation = step_operation(db, active)
            if operation.state not in {"failed", "blocked", "cancelled"}:
                return operation
            # A dispatcher-exhausted lease can leave an epoch without a final page callback.
            apply(
                db, active.id, active.cursor, DiscoveryResult(issues=["discovery_step_interrupted"])
            )
            return step_operation(db, active) if active.state == "running" else None
        active.state = "expired"
        active.finished_at = now()
    company.discovery_due_at = now() + timedelta(days=1)
    initial = target(company.website) if company.website else search_target(company.label)
    run = DiscoveryRun(
        company_id=company.id,
        company_revision=company.revision,
        frontier=[initial.model_dump()],
    )
    db.add(run)
    db.flush()
    return step_operation(db, run)


def schedule(db: Session, limit: int = 100) -> int:
    companies = db.scalars(
        select(Company)
        .where(~Company.paused, Company.discovery_due_at <= now())
        .order_by(Company.discovery_due_at, Company.id)
        .with_for_update(skip_locked=True)
        .limit(limit)
    )
    return sum(begin(db, company) is not None for company in companies)


def prepare(run_id: UUID, cursor: int) -> DiscoveryResult:
    with Session(get_engine()) as db:
        run = db.get(DiscoveryRun, run_id)
        company = db.get(Company, run.company_id) if run else None
        if (
            run is None
            or company is None
            or company.paused
            or run.state != "running"
            or run.cursor != cursor
            or run.company_revision != company.revision
            or run.started_at <= now() - timedelta(hours=24)
        ):
            raise OperationError("discovery_superseded", "This discovery run is no longer current.")
        item = Target.model_validate(run.frontier[cursor])
        website = company.website
    if item.query is not None:
        from app.collection.search import search

        candidates = search(run_id, item.search_slot, item.query)
        return DiscoveryResult(
            candidates=candidates, issues=["search_candidates_unverified"] if candidates else []
        )
    assert website is not None
    if item.adapter and item.board:
        decoded = decode_page(item.adapter, fetch_json(item.url))
        if decoded.issues:
            return DiscoveryResult(issues=["ats_response_unverified", *decoded.issues])
        # A valid empty board is a verified source; pagination is collected independently.
        return DiscoveryResult(verified=item)
    document = fetch_document(FetchRequest(url=item.url))
    if document.status != 200:
        raise OperationError(
            "discovery_http_error",
            "A discovery page could not be read.",
            retryable=document.status == 429 or document.status >= 500,
            retry_after=min(document.retry_after or 60, 30 * 86400),
        )
    redirected = target(document.url, depth=item.depth, linked_from=item.url)
    if redirected.adapter:
        return DiscoveryResult(links=[redirected])
    if not same_site(document.url, website):
        return DiscoveryResult(issues=["unverified_redirect"])
    if document.content_type.split(";", 1)[0].strip().lower() not in {
        "text/html",
        "application/xhtml+xml",
    }:
        return DiscoveryResult(issues=["discovery_content_type"])
    page = parse_page(document.body, document.url)
    result = DiscoveryResult(
        issues=[issue for issue in page.issues if issue != "no_structured_jobs"]
    )
    for found in page.candidates[:50]:
        result.candidates.append(
            {
                "url": found.posting.url,
                "title": found.posting.title,
                "employer": found.employer_name,
                "source_url": found.source_url,
                "evidence_path": found.evidence_path,
                "status": "generic_collection_pending",
            }
        )
    if page.candidates:
        result.issues.append("generic_collection_pending")
    for entry in page.links:
        proposed = target(entry.url, depth=item.depth + 1, linked_from=document.url)
        if proposed.adapter:
            result.links.append(proposed)
        elif (
            item.depth < 2
            and same_site(entry.url, website)
            and re.search(
                r"career|\bjobs?\b|vacanc|opportunit|join[- /]us|work[- /]with",
                entry.label + " " + entry.url,
                re.I,
            )
        ):
            result.links.append(proposed)
    return result


def apply(db: Session, run_id: UUID, cursor: int, result: DiscoveryResult) -> None:
    initial = db.get(DiscoveryRun, run_id)
    if initial is None:
        return
    company = db.get(Company, initial.company_id, with_for_update=True)
    run = db.get(DiscoveryRun, run_id, with_for_update=True, populate_existing=True)
    assert run is not None and company is not None
    if run.state != "running" or run.cursor != cursor:
        return
    if (
        company.paused
        or company.revision != run.company_revision
        or run.started_at <= now() - timedelta(hours=24)
    ):
        run.state = "cancelled"
        run.finished_at = now()
        return
    issues = set(run.issues) | set(result.issues)
    if result.verified:
        item = result.verified
        existing = db.scalar(
            select(Source).where(Source.company_id == company.id, Source.identity == key(item.url))
        )
        if existing is None:
            db.add(
                Source(
                    company_id=company.id,
                    identity=key(item.url),
                    adapter=item.adapter,
                    config={"board": item.board, "region": item.region},
                    url=item.url,
                    interval_hours=company.interval_hours,
                    authoritative=True,
                    evidence={
                        "basis": "official_site_link" if item.linked_from else "owner_website",
                        "linked_from": item.linked_from,
                        "network_verified": True,
                        "discovery_run_id": str(run.id),
                    },
                )
            )
    frontier = list(run.frontier)
    seen = {entry["url"] for entry in frontier}
    for entry in result.links:
        if entry.url in seen:
            continue
        if len(frontier) >= MAX_PAGES:
            issues.add("discovery_page_limit")
            break
        seen.add(entry.url)
        frontier.append(entry.model_dump())
    run.frontier = frontier
    run.candidates = [*run.candidates, *result.candidates][:100]
    if len(run.candidates) == 100:
        issues.add("discovery_candidate_limit")
    run.issues = sorted(issues)
    run.cursor += 1
    if run.cursor < len(frontier):
        step_operation(db, run)
        return
    db.flush()
    has_source = (
        db.scalar(select(Source.id).where(Source.company_id == company.id).limit(1)) is not None
    )
    if not has_source and not any(entry.get("query") for entry in frontier):
        run.frontier = [*frontier, search_target(company.label).model_dump()]
        step_operation(db, run)
        return
    run.state = "partial" if issues else "complete"
    run.finished_at = now()
    company.resolution = (
        "sources_found"
        if has_source
        else (
            "needs_review"
            if any(entry.get("status") == "needs_identity_review" for entry in run.candidates)
            else "unresolved"
        )
    )
    company.evidence = {
        **company.evidence,
        "discovery_run_id": str(run.id),
        "discovery_issues": run.issues,
        "candidate_count": len(run.candidates),
    }
    company.discovery_due_at = now() + timedelta(days=7 if has_source else 1)
