"""Generic structured job collection with explicit employer attribution."""

import re
import unicodedata

from app.collection.contracts import InventoryPage
from app.collection.generic import GenericPage, JobCandidate, parse_page
from app.collection.transport import fetch_document
from app.fetcher.contracts import FetchRequest
from app.services.operations import OperationError


def same_site(url: str, website: str) -> bool:
    from app.collection.discovery import same_site as compare

    return compare(url, website)


def name_key(value: str) -> str:
    return " ".join(re.findall(r"\w+", unicodedata.normalize("NFKC", value).casefold()))


def belongs(candidate: JobCandidate, company_name: str, website: str) -> bool:
    # A job is never attributed solely because a search engine returned its URL.
    if candidate.employer_url and same_site(candidate.employer_url, website):
        return True
    if candidate.employer_name:
        return name_key(candidate.employer_name) == name_key(company_name)
    # Missing structured employer evidence needs later owner/AI review.
    return False


def inventory(page: GenericPage, company_name: str, website: str) -> InventoryPage:
    issues = set(page.issues)
    postings = []
    for candidate in page.candidates:
        if not belongs(candidate, company_name, website):
            issues.add("job_employer_unverified")
            continue
        if candidate.expired is True:
            issues.add("expired_job_evidence")
            continue
        postings.append(candidate.posting)
    if not postings:
        issues.add("no_verified_generic_jobs")
    # Complete here means this page was parsed, never exhaustive company coverage.
    # The Source must be non-authoritative; no omissions may close jobs.
    return InventoryPage(
        postings=postings, complete=bool(postings) and not issues, issues=sorted(issues)
    )


def collect(url: str, company_name: str, website: str) -> InventoryPage:
    document = fetch_document(FetchRequest(url=url))
    if document.status != 200:
        raise OperationError(
            "generic_http_error",
            "The job page could not be checked.",
            retryable=document.status == 429 or document.status >= 500,
            retry_after=min(document.retry_after or 60, 30 * 86400),
        )
    if not same_site(document.url, website):
        raise OperationError(
            "generic_redirect_unverified", "The job page moved to an unverified site."
        )
    if document.content_type.split(";", 1)[0].lower().strip() not in {
        "text/html",
        "application/xhtml+xml",
    }:
        raise OperationError("generic_content_type", "The job page did not return HTML.")
    page = parse_page(document.body, document.url)
    result = inventory(page, company_name, website)
    collected_urls = {posting.url for posting in result.postings}
    links = [
        entry.url
        for entry in page.links
        if entry.url not in collected_urls
        and same_site(entry.url, website)
        and (
            "next" in entry.relation or re.search(r"/(jobs?|careers?|positions?)/", entry.url, re.I)
        )
    ]
    result.next_urls = list(dict.fromkeys(links))[:200]
    if len(set(links)) > 200:
        result.issues.append("generic_link_limit")
        result.complete = False
    return result
