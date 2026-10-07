"""Bounded, offline JobPosting JSON-LD and link extraction.

Schema contract: https://schema.org/JobPosting. Results are candidates, not
verified employer associations or an authoritative inventory. Never fetch @context.
"""

import json
import re
from datetime import UTC, date, datetime
from typing import Any
from urllib.parse import urljoin

from app.collection.ats import plain
from app.collection.contracts import Posting, public_link
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field

MAX_HTML = 10 * 1024 * 1024
MAX_NODES = 20_000
MAX_JOBS = 500
MAX_LINKS = 1000
MAX_VISIBLE = 100_000


class JobCandidate(BaseModel):
    posting: Posting
    employer_name: str | None = None
    employer_url: str | None = None
    source_url: str
    evidence_path: str
    advertised_date: str | None = None
    valid_through: str | None = None
    expired: bool | None = None
    applicant_locations: list[str] = Field(default_factory=list)


class PageLink(BaseModel):
    url: str
    label: str
    relation: list[str] = Field(default_factory=list)


class GenericPage(BaseModel):
    empty_confirmed: bool = False
    candidates: list[JobCandidate] = Field(default_factory=list)
    links: list[PageLink] = Field(default_factory=list)
    visible_text: str = ""
    issues: list[str] = Field(default_factory=list)
    # Traversal/identity verification must be performed by the collecting operation.
    authoritative: bool = False


def scalar(value: Any) -> str | None:
    return (value.strip() or None) if isinstance(value, str) else None


def values(value: Any) -> list[Any]:
    return value if isinstance(value, list) else [value] if value is not None else []


def label(value: Any) -> str | None:
    return scalar(value.get("name")) if isinstance(value, dict) else scalar(value)


def link(value: Any, base: str) -> str | None:
    if isinstance(value, dict):
        value = value.get("@id") or value.get("url")
    if not isinstance(value, str) or not value.strip():
        return None
    return public_link(urljoin(base, value.strip()))


def timestamp(value: Any) -> datetime | None:
    raw = scalar(value)
    if not raw:
        return None
    try:
        result = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    # Do not invent an instant/timezone for a calendar date or local time.
    return result if result.tzinfo is not None else None


def expiry(raw: str | None, now: datetime) -> bool | None:
    if raw is None:
        return None
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        try:
            # Date-only expiry is not considered past until the whole UTC date ends.
            return date.fromisoformat(raw) < now.astimezone(UTC).date()
        except ValueError:
            return None
    instant = timestamp(raw)
    return instant < now if instant else None


def place(value: Any) -> str | None:
    if not isinstance(value, dict):
        return scalar(value)
    address = value.get("address")
    if isinstance(address, dict):
        parts = [
            label(address.get(key))
            for key in ("addressLocality", "addressRegion", "addressCountry")
        ]
        return ", ".join(dict.fromkeys(part for part in parts if part)) or label(value)
    return scalar(address) or label(value)


def candidate(
    row: dict[str, Any],
    source: str,
    path: str,
    *,
    single: bool,
    references: dict[str, dict[str, Any]],
    now: datetime,
) -> JobCandidate:
    url = link(row.get("url"), source) or link(row.get("mainEntityOfPage"), source)
    if url is None and single:
        url = source
    if url is None:
        raise ValueError("Multiple jobs need separate detail URLs.")
    identifier = row.get("identifier")
    if isinstance(identifier, dict):
        identifier = identifier.get("value")
    if type(identifier) is int:
        identifier = str(identifier)
    organization = row.get("hiringOrganization")
    if isinstance(organization, dict) and set(organization) == {"@id"}:
        organization = references.get(organization["@id"], organization)
    employer_url = None
    if isinstance(organization, dict):
        try:
            employer_url = link(organization.get("url") or organization.get("sameAs"), source)
        except ValueError:
            pass  # Invalid optional metadata must never become a fetch destination.
    salary = row.get("baseSalary")
    valid_through = scalar(row.get("validThrough"))
    return JobCandidate(
        posting=Posting(
            external_id=scalar(identifier) or url,
            title=plain(scalar(row.get("title")) or ""),
            url=url,
            apply_url=url,
            description=plain(scalar(row.get("description")) or ""),
            locations=list(
                dict.fromkeys(p for x in values(row.get("jobLocation")) if (p := place(x)))
            ),
            workplace=scalar(row.get("jobLocationType")),
            employment_type=", ".join(
                x for v in values(row.get("employmentType")) if (x := scalar(v))
            )
            or None,
            department=label(row.get("employmentUnit")),
            salary=salary if isinstance(salary, dict) else None,
            published_at=timestamp(row.get("datePosted")),
        ),
        employer_name=label(organization),
        employer_url=employer_url,
        source_url=source,
        evidence_path=path,
        advertised_date=scalar(row.get("datePosted")),
        valid_through=valid_through,
        expired=expiry(valid_through, now),
        applicant_locations=list(
            dict.fromkeys(
                p for x in values(row.get("applicantLocationRequirements")) if (p := place(x))
            )
        ),
    )


def parse_page(body: str, source_url: str, *, now: datetime | None = None) -> GenericPage:
    source_url = public_link(source_url)
    now = now or datetime.now(UTC)
    if now.tzinfo is None:
        raise ValueError("The observation time needs a timezone.")
    result = GenericPage()
    if len(body.encode("utf-8")) > MAX_HTML:
        result.issues.append("html_limit")
        return result
    soup = BeautifulSoup(body, "lxml")
    rows: list[tuple[dict[str, Any], str]] = []
    references: dict[str, dict[str, Any]] = {}
    visited = 0
    for index, script in enumerate(soup.find_all("script", type="application/ld+json")):
        try:
            document = json.loads(script.get_text())
        except (ValueError, RecursionError):
            result.issues.append("invalid_json_ld")
            continue
        stack: list[tuple[Any, str, int]] = [(document, f"json_ld[{index}]", 0)]
        while stack:
            node, path, depth = stack.pop()
            visited += 1
            if visited > MAX_NODES or depth > 60:
                result.issues.append("structured_data_limit")
                stack.clear()
                break
            if isinstance(node, dict):
                identifier = scalar(node.get("@id"))
                if identifier and len(node) > 1:
                    if identifier in references and references[identifier] != node:
                        result.issues.append("ambiguous_reference")
                    else:
                        references[identifier] = node
                if any(
                    t
                    in {
                        "JobPosting",
                        "https://schema.org/JobPosting",
                        "http://schema.org/JobPosting",
                    }
                    for t in values(node.get("@type"))
                    if isinstance(t, str)
                ):
                    rows.append((node, path))
                for key, child in reversed(list(node.items())):
                    if isinstance(child, (dict, list)) and key != "@context":
                        stack.append((child, f"{path}.{key}", depth + 1))
            elif isinstance(node, list):
                for offset in range(len(node) - 1, -1, -1):
                    stack.append((node[offset], f"{path}[{offset}]", depth + 1))
        if visited > MAX_NODES:
            break
    if len(rows) > MAX_JOBS:
        result.issues.append("job_limit")
    seen: dict[str, JobCandidate] = {}
    for row, path in rows[:MAX_JOBS]:
        try:
            found = candidate(
                row, source_url, path, single=len(rows) == 1, references=references, now=now
            )
        except (ValueError, TypeError, KeyError):
            result.issues.append("invalid_job_posting")
            continue
        previous = seen.get(found.posting.url)
        if previous:
            if (
                previous.posting.content_hash() != found.posting.content_hash()
                or previous.employer_name != found.employer_name
                or previous.employer_url != found.employer_url
                or previous.valid_through != found.valid_through
            ):
                result.issues.append("conflicting_job_posting")
            continue
        seen[found.posting.url] = found
        result.candidates.append(found)
    if not rows:
        result.issues.append("no_structured_jobs")
    for element in soup(["script", "style", "noscript", "template", "svg"]):
        element.decompose()
    for element in soup.select('[hidden], [aria-hidden="true"]'):
        if element.parent is not None:
            element.decompose()
    seen_links: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        try:
            url = link(anchor.get("href"), source_url)
        except ValueError:
            continue
        if not url or url in seen_links:
            continue
        if len(result.links) >= MAX_LINKS:
            result.issues.append("link_limit")
            break
        seen_links.add(url)
        relation = anchor.get("rel")
        result.links.append(
            PageLink(
                url=url,
                label=anchor.get_text(" ", strip=True)[:1000],
                relation=relation if isinstance(relation, list) else [],
            )
        )
    visible = "\n".join(x.strip() for x in soup.get_text("\n").splitlines() if x.strip())
    if len(visible) > MAX_VISIBLE:
        result.issues.append("visible_text_limit")
    result.visible_text = visible[:MAX_VISIBLE]
    result.issues = sorted(set(result.issues))
    return result
