"""Public ATS decoding. The caller supplies fetched JSON through the isolated fetcher.

Source contracts: docs.greenhouse.io/job-board.html,
 github.com/lever/postings-api, developers.ashbyhq.com/docs/public-job-posting-api.
No network requests, database writes, filtering or inference take place here.
"""

import html
import re
from typing import Any

from app.collection.contracts import Adapter, InventoryPage, Posting, public_link
from bs4 import BeautifulSoup
from pydantic import ValidationError

PAGE_SIZE = 100


def request_url(adapter: Adapter, board: str, *, region: str = "global", offset: int = 0) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", board) or offset < 0:
        raise ValueError("Invalid board identifier or continuation offset.")
    if adapter == "greenhouse":
        return f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true"
    if adapter == "ashby":
        return f"https://api.ashbyhq.com/posting-api/job-board/{board}?includeCompensation=true"
    if adapter != "lever" or region not in {"global", "eu"}:
        raise ValueError("Unsupported ATS or region.")
    host = "api.eu.lever.co" if region == "eu" else "api.lever.co"
    return f"https://{host}/v0/postings/{board}?mode=json&skip={offset}&limit={PAGE_SIZE}"


def plain(value: str) -> str:
    # Greenhouse HTML is sometimes entity-encoded. Decode once before parsing.
    soup = BeautifulSoup(html.unescape(value), "lxml")
    for element in soup(["script", "style", "noscript", "template"]):
        element.decompose()
    return "\n".join(line.strip() for line in soup.get_text("\n").splitlines() if line.strip())


def text(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("Expected text.")
    return value.strip()


def optional(value: Any) -> str | None:
    return (text(value) or None) if value is not None else None


def locations(values: list[Any]) -> list[str]:
    return sorted({text(value) for value in values if value is not None and text(value)})


def decode_row(adapter: Adapter, row: dict[str, Any]) -> Posting | None:
    if adapter == "greenhouse":
        identifier = row["id"]
        if isinstance(identifier, bool) or not isinstance(identifier, (str, int)):
            raise ValueError("Invalid posting ID.")
        return Posting(
            external_id=str(identifier),
            title=text(row["title"]),
            url=row["absolute_url"],
            apply_url=row["absolute_url"],
            description=plain(text(row["content"])),
            locations=locations([row.get("location", {}).get("name")]),
        )
    if adapter == "lever":
        categories = row.get("categories", {})
        sections = [row.get("descriptionPlain") or plain(text(row.get("description", "")))]
        for section in row.get("lists", []):
            sections.extend([text(section["text"]), plain(text(section["content"]))])
        sections.extend(
            [
                row.get("additionalPlain") or plain(text(row.get("additional", ""))),
                row.get("salaryDescriptionPlain") or plain(text(row.get("salaryDescription", ""))),
            ]
        )
        salary = row.get("salaryRange")
        return Posting(
            external_id=text(row["id"]),
            title=text(row["text"]),
            url=row["hostedUrl"],
            apply_url=row["applyUrl"],
            description="\n".join(text(section) for section in sections if section),
            locations=locations([categories.get("location"), *categories.get("allLocations", [])]),
            workplace=optional(row.get("workplaceType")),
            employment_type=optional(categories.get("commitment")),
            department=optional(categories.get("department") or categories.get("team")),
            salary=salary,
        )
    if adapter != "ashby":
        raise ValueError("Unsupported ATS.")
    if row["isListed"] is False:
        return None
    if row["isListed"] is not True:
        raise ValueError("Missing publication visibility.")
    # The documented API does not promise a separate ID; its canonical job URL is stable.
    return Posting(
        external_id=public_link(text(row["jobUrl"])),
        title=text(row["title"]),
        url=row["jobUrl"],
        apply_url=row["applyUrl"],
        description=text(row.get("descriptionPlain") or plain(text(row["descriptionHtml"]))),
        locations=locations(
            [row.get("location"), *[x.get("location") for x in row.get("secondaryLocations", [])]]
        ),
        workplace=optional(row.get("workplaceType")),
        employment_type=optional(row.get("employmentType")),
        department=optional(row.get("department")),
        published_at=row.get("publishedAt"),
        salary=row.get("compensation"),
    )


def decode_page(adapter: Adapter, payload: Any, *, offset: int = 0) -> InventoryPage:
    """Malformed responses are incomplete, never an authoritative empty inventory."""
    if adapter not in {"greenhouse", "lever", "ashby"} or offset < 0:
        raise ValueError("Invalid adapter or continuation offset.")
    issues: list[str] = []
    if adapter == "lever":
        rows = payload
    elif isinstance(payload, dict):
        rows = payload.get("jobs")
        if adapter == "ashby" and payload.get("apiVersion") != "1":
            issues.append("unsupported_api_version")
    else:
        rows = None
    if not isinstance(rows, list):
        return InventoryPage(postings=[], complete=False, issues=["invalid_inventory"])
    if len(rows) > 20_000 or (adapter == "lever" and len(rows) > PAGE_SIZE):
        return InventoryPage(postings=[], complete=False, issues=["inventory_limit"])
    if adapter == "greenhouse":
        total = (
            payload.get("meta", {}).get("total") if isinstance(payload.get("meta"), dict) else None
        )
        if type(total) is not int or total != len(rows):
            issues.append("inventory_count_unverified")
    postings: list[Posting] = []
    seen: set[str] = set()
    for row in rows:
        try:
            if not isinstance(row, dict):
                raise ValueError("Invalid posting.")
            posting = decode_row(adapter, row)
            if posting is None:
                continue
            if posting.external_id in seen:
                issues.append("duplicate_posting")
                continue
            seen.add(posting.external_id)
            postings.append(posting)
        except (KeyError, TypeError, ValueError, AttributeError, ValidationError):
            issues.append("invalid_posting")
    next_offset = offset + len(rows) if adapter == "lever" and len(rows) == PAGE_SIZE else None
    return InventoryPage(
        postings=postings,
        complete=not issues and next_offset is None,
        next_offset=next_offset,
        issues=sorted(set(issues)),
    )
