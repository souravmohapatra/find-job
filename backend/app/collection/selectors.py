"""Bounded, declarative public-page extraction; selectors never execute page code."""

import re
from datetime import UTC, datetime
from typing import Annotated, Literal

from app.collection.contracts import Posting, public_link
from app.collection.generic import (
    MAX_HTML,
    MAX_JOBS,
    MAX_NODES,
    GenericPage,
    JobCandidate,
    PageLink,
    expiry,
    link,
)
from bs4 import BeautifulSoup, Tag
from pydantic import BaseModel, ConfigDict, Field, field_validator

Selector = Annotated[str, Field(min_length=1, max_length=256)]


class SelectorRules(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    cards: Selector
    title: Selector
    link: Selector
    description: Selector
    employer: Selector
    employer_scope: Literal["card", "page"] = "card"
    location: Selector | None = None
    next_page: Selector | None = None
    empty: Selector | None = None
    closed: Selector | None = None
    valid_through: Selector | None = None

    @field_validator(
        "cards",
        "title",
        "link",
        "description",
        "employer",
        "location",
        "next_page",
        "empty",
        "closed",
        "valid_through",
    )
    @classmethod
    def bounded_selector(cls, value: str | None) -> str | None:
        if value is None or value == ":scope":
            return value
        # Deliberately omit recursive pseudo-classes, escapes, selector lists and scripts.
        if not re.fullmatch(r"[A-Za-z0-9_\-\s.#>\[\]=\"'*]+", value) or len(value.split()) > 8:
            raise ValueError(
                "Use a short tag, class, ID or attribute selector, "
                "optionally with child/descendant steps."
            )
        try:
            BeautifulSoup("", "lxml").select(value, limit=1)
        except Exception as error:
            raise ValueError("This selector is not valid.") from error
        return value


def select(root: Tag, selector: str, limit: int) -> list[Tag]:
    return [root] if selector == ":scope" else list(root.select(selector, limit=limit))


def one(root: Tag, selector: str) -> Tag:
    matches = select(root, selector, 2)
    if len(matches) != 1:
        raise ValueError("Field must select exactly one element.")
    return matches[0]


def text(root: Tag, selector: str) -> str:
    value = one(root, selector).get_text(" ", strip=True)
    if not value:
        raise ValueError("Selected field is empty.")
    return value


def parse(
    body: str, source_url: str, rules: SelectorRules, *, instant: datetime | None = None
) -> GenericPage:
    source_url = public_link(source_url)
    instant = instant or datetime.now(UTC)
    if instant.tzinfo is None:
        raise ValueError("An aware time is required.")
    result = GenericPage()
    if len(body.encode("utf-8")) > MAX_HTML:
        result.issues.append("html_limit")
        return result
    soup = BeautifulSoup(body, "lxml")
    if len(soup.find_all(limit=MAX_NODES + 1)) > MAX_NODES:
        result.issues.append("selector_node_limit")
        return result
    for element in soup(["script", "style", "noscript", "template", "svg"]):
        element.decompose()
    for element in soup.select('[hidden], [aria-hidden="true"]'):
        if element.parent is not None:
            element.decompose()
    cards = select(soup, rules.cards, MAX_JOBS + 1)
    empty = bool(
        rules.empty and any(node.get_text(" ", strip=True) for node in select(soup, rules.empty, 2))
    )
    if cards and empty:
        result.issues.append("selector_empty_conflict")
    if len(cards) > MAX_JOBS:
        result.issues.append("job_limit")
    seen: dict[str, JobCandidate] = {}
    conflicts: set[str] = set()
    for index, card in enumerate(cards[:MAX_JOBS]):
        if rules.closed and select(card, rules.closed, 1):
            result.issues.append("selector_closed_listing")
            continue
        try:
            url = link(one(card, rules.link).get("href"), source_url)
            if not url:
                raise ValueError("A public detail link is required.")
            valid_through = None
            if rules.valid_through:
                date_node = one(card, rules.valid_through)
                raw = date_node.get("datetime")
                valid_through = raw if isinstance(raw, str) else date_node.get_text(" ", strip=True)
                if expiry(valid_through, instant) is None:
                    raise ValueError("Invalid expiry value.")
            found = JobCandidate(
                posting=Posting(
                    external_id=url,
                    url=url,
                    apply_url=url,
                    title=text(card, rules.title),
                    description=text(card, rules.description),
                    locations=[text(card, rules.location)] if rules.location else [],
                ),
                employer_name=text(
                    soup if rules.employer_scope == "page" else card, rules.employer
                ),
                source_url=source_url,
                evidence_path=f"selectors.cards[{index}]",
                valid_through=valid_through,
                expired=expiry(valid_through, instant),
            )
        except (ValueError, TypeError):
            result.issues.append("selector_card_invalid")
            continue
        if url in seen and (
            seen[url].posting != found.posting
            or seen[url].employer_name != found.employer_name
            or seen[url].valid_through != found.valid_through
        ):
            conflicts.add(url)
            result.issues.append("selector_conflicting_job")
        seen.setdefault(url, found)
    result.candidates = [candidate for url, candidate in seen.items() if url not in conflicts]
    result.empty_confirmed = not cards and empty
    if not cards and not empty:
        result.issues.append("selector_no_cards")
    if rules.next_page:
        next_links = select(soup, rules.next_page, 201)
        if len(next_links) > 200:
            result.issues.append("selector_pagination_limit")
        visited: set[str] = set()
        for anchor in next_links[:200]:
            try:
                url = link(anchor.get("href"), source_url)
                if not url:
                    raise ValueError("Missing pagination link.")
            except ValueError:
                result.issues.append("selector_pagination_invalid")
                continue
            if url not in visited:
                result.links.append(
                    PageLink(
                        url=url, label=anchor.get_text(" ", strip=True)[:1000], relation=["next"]
                    )
                )
                visited.add(url)
    result.issues = sorted(set(result.issues))
    return result
