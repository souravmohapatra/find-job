from datetime import UTC, datetime, timedelta

import pytest
from app.collection import generic_inventory
from app.collection.cache import key
from app.collection.extraction_input import PreparedPage
from app.collection.models import Source, SourceSnapshot
from app.collection.selectors import SelectorRules, parse
from app.db import get_engine
from app.fetcher.contracts import FetchResult
from app.profile_models import now
from pydantic import ValidationError
from sqlalchemy.orm import Session
from test_inventory import source
from test_inventory_api import auth

URL = "https://example.com/careers"
RULES = dict(cards=".job", title="h2", link="a", description=".description", employer=".employer")
CARD = """<article class="job"><h2>Strategy manager</h2><a href="/jobs/one">Apply</a>
<p class="description">Plan markets <span hidden>hidden text</span><script>bad()</script></p>
<span class="employer">Example</span></article>"""


def result(body=CARD, **changes):
    return generic_inventory.collect(
        URL,
        "Example",
        "https://example.com",
        document=FetchResult(url=URL, status=200, content_type="text/html", body=body),
        rules=SelectorRules(**(RULES | changes)),
    )


def test_rules_extract_visible_fields_and_verify_employer():
    page = result()
    assert page.complete and len(page.postings) == 1
    assert page.postings[0].description == "Plan markets"
    assert page.postings[0].url == "https://example.com/jobs/one"
    assert not result(CARD.replace("Example", "Other")).postings
    page = result(
        CARD.replace('<span class="employer">Example</span>', "") + "<header>Example</header>",
        employer="header",
        employer_scope="page",
    )
    assert page.complete


@pytest.mark.parametrize(
    "selector", [".job:has(a)", ".job, article", "[", "a + p", "a\\31", "a" * 257]
)
def test_rules_reject_unbounded_or_unsupported_selectors(selector):
    with pytest.raises(ValidationError):
        SelectorRules(**(RULES | {"cards": selector}))


@pytest.mark.parametrize(
    "body",
    [
        CARD.replace("<h2>Strategy manager</h2>", ""),
        CARD.replace("</h2>", "</h2><h2>Ambiguous</h2>"),
        CARD.replace("/jobs/one", "http://127.0.0.1/admin"),
        CARD.replace("/jobs/one", "javascript:alert(1)"),
    ],
)
def test_invalid_fields_are_visible_failures_without_ai_fallback(body):
    page = result(body)
    assert not page.complete and not page.postings
    assert "selector_card_invalid" in page.issues
    assert not isinstance(page, PreparedPage)


def test_empty_state_must_be_explicit_and_cannot_contradict_cards():
    assert not result("<p>No roles</p>").complete
    empty = result('<p class="empty">No roles</p>', empty=".empty")
    assert empty.complete and not empty.postings
    assert not result('<p class="empty"></p>', empty=".empty").complete
    conflict = result(CARD + '<p class="empty">No roles</p>', empty=".empty")
    assert not conflict.complete and "selector_empty_conflict" in conflict.issues


def test_duplicate_conflicting_jobs_are_withheld():
    assert len(result(CARD * 2).postings) == 1
    page = result(CARD + CARD.replace("Strategy manager", "Legal counsel"))
    assert not page.postings and "selector_conflicting_job" in page.issues


def test_expiry_closed_markers_and_pagination():
    assert not result(
        CARD.replace("</article>", '<time datetime="2000-01-01"></time></article>'),
        valid_through="time",
    ).postings
    assert not result(CARD, closed="h2").postings
    page = result(
        CARD
        + '<a class="next" href="?page=2">Next</a><a class="next" href="https://other.example/jobs">Other</a>',
        next_page=".next",
    )
    assert page.next_urls == [URL + "?page=2"]
    assert "selector_external_pagination" in page.issues
    with pytest.raises(ValueError, match="aware"):
        parse(CARD, URL, SelectorRules(**RULES), instant=datetime(2026, 1, 1))
    assert parse(
        CARD, URL, SelectorRules(**RULES), instant=datetime(2026, 1, 1, tzinfo=UTC)
    ).candidates


def website_source():
    with Session(get_engine()) as db, db.begin():
        row = source(db)
        row.adapter = "generic_http"
        row.authoritative = False
        row.url = URL
        row.config = {"company_name": "Example", "website": "https://example.com"}
        return row.id


def test_rules_api_revision_protection_save_clear_and_ats_rejection(client):
    identifier = website_source()
    path = f"/api/v1/sources/{identifier}/rules"
    body = {"rules": RULES}
    assert client.put(path, json=body).status_code == 401
    headers = auth(client)
    assert client.put(path, headers=headers, json=body).status_code == 428
    saved = client.put(path, headers=headers | {"If-Match": '"1"'}, json=body)
    assert saved.status_code == 200 and saved.json()["rules"]["cards"] == ".job"
    assert client.put(path, headers=headers | {"If-Match": '"1"'}, json=body).status_code == 409
    assert (
        client.put(path, headers=headers | {"If-Match": '"2"'}, json={"rules": None}).status_code
        == 200
    )
    with Session(get_engine()) as db, db.begin():
        row = db.get(Source, identifier)
        assert row.config == {"company_name": "Example", "website": "https://example.com"}
        assert row.revision == 3 and not row.authoritative
        row.adapter = "lever"
    assert client.put(path, headers=headers | {"If-Match": '"3"'}, json=body).status_code == 422


def test_preview_uses_only_recent_valid_saved_page_and_never_writes_rules(client, monkeypatch):
    def unexpected(*args, **kwargs):
        pytest.fail("Preview must not fetch")

    monkeypatch.setattr(generic_inventory, "fetch_document", unexpected)
    identifier = website_source()
    path = f"/api/v1/sources/{identifier}/rules/preview"
    headers = auth(client) | {"If-Match": '"1"'}
    body = {"rules": RULES}
    assert client.post(path, headers=headers, json=body).status_code == 409
    with Session(get_engine()) as db, db.begin():
        db.add(
            SourceSnapshot(
                source_id=identifier,
                url_hash=key(URL),
                source_revision=1,
                document=FetchResult(
                    url=URL, status=200, content_type="text/html", body=CARD
                ).model_dump(mode="json"),
                body_hash=key(CARD),
                fetched_at=now(),
            )
        )
    preview = client.post(path, headers=headers, json=body)
    assert preview.status_code == 200
    assert preview.json()["accepted_jobs"] == 1 and preview.json()["complete"]
    with Session(get_engine()) as db, db.begin():
        row = db.get(Source, identifier)
        assert row.revision == 1 and "rules" not in row.config
        snapshot = db.get(SourceSnapshot, (identifier, key(URL)))
        snapshot.document = {"broken": True}
    assert client.post(path, headers=headers, json=body).status_code == 409
    with Session(get_engine()) as db, db.begin():
        db.get(SourceSnapshot, (identifier, key(URL))).fetched_at = now() - timedelta(days=8)
    assert client.post(path, headers=headers, json=body).status_code == 409


def test_worker_uses_saved_rules_and_empty_checks_never_close_jobs(monkeypatch):
    from app.collection.inventory import begin_run
    from app.collection.models import Job, JobSource, PageExtraction
    from app.profile_models import Operation
    from app.services.operations import process_operation
    from sqlalchemy import func, select

    identifier = website_source()
    with Session(get_engine()) as db, db.begin():
        row = db.get(Source, identifier)
        row.config = row.config | {"rules": RULES | {"empty": ".empty"}}
    bodies = [CARD]
    monkeypatch.setattr(
        generic_inventory,
        "fetch_document",
        lambda request: FetchResult(
            url=request.url, status=200, content_type="text/html", body=bodies[0]
        ),
    )
    for body in [CARD] + ['<p class="empty">No vacancies</p>'] * 3:
        bodies[0] = body
        with Session(get_engine()) as db, db.begin():
            operation_id = begin_run(db, db.get(Source, identifier)).id
        process_operation(operation_id)
        with Session(get_engine()) as db:
            assert db.get(Operation, operation_id).state == "succeeded"
    with Session(get_engine()) as db:
        assert db.scalar(select(Job)).availability == "active"
        assert db.scalar(select(JobSource)).omissions == 0
        assert db.scalar(select(func.count()).select_from(PageExtraction)) == 0
        assert db.get(Source, identifier).last_error is None
