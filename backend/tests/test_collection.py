from copy import deepcopy

import pytest
from app.collection.ats import PAGE_SIZE, decode_page, request_url
from app.collection.contracts import public_link


def lever(identifier: str = "one") -> dict:
    return {
        "id": identifier,
        "text": "Legal adviser",
        "categories": {"location": "London", "allLocations": ["London", "Paris"]},
        "descriptionPlain": "Advise on commercial contracts.",
        "lists": [{"text": "Requirements", "content": "<ul><li>Legal qualification</li></ul>"}],
        "additionalPlain": "Flexible hours.",
        "salaryRange": {"currency": "GBP", "interval": "year", "min": 80000, "max": 95000},
        "hostedUrl": f"https://jobs.lever.co/example/{identifier}?utm_source=test",
        "applyUrl": f"https://jobs.lever.co/example/{identifier}/apply",
    }


def test_greenhouse_complete_empty_and_malformed_are_distinct() -> None:
    assert decode_page("greenhouse", {"jobs": [], "meta": {"total": 0}}).complete
    for payload in [{}, {"jobs": []}, {"jobs": [], "meta": {"total": 2}}, {"jobs": [None]}]:
        assert not decode_page("greenhouse", payload).complete
    result = decode_page(
        "greenhouse",
        {
            "jobs": [
                {
                    "id": 17,
                    "title": "Strategy manager",
                    "location": {"name": "London"},
                    "absolute_url": "https://example.com/job?gh_jid=17&utm_medium=test#apply",
                    "content": "&lt;p&gt;Lead planning&lt;/p&gt;<script>malicious()</script>",
                }
            ],
            "meta": {"total": 1},
        },
    )
    assert result.complete
    job = result.postings[0]
    assert job.external_id == "17" and job.description == "Lead planning"
    assert job.url == "https://example.com/job?gh_jid=17"


def test_lever_pagination_retains_unrelated_roles_and_all_description_sections() -> None:
    rows = [lever(str(index)) for index in range(PAGE_SIZE)]
    first = decode_page("lever", rows)
    assert first.next_offset == PAGE_SIZE and not first.complete
    assert first.issues == []
    assert decode_page("lever", [], offset=PAGE_SIZE).complete
    assert request_url("lever", "example", region="eu", offset=100) == (
        "https://api.eu.lever.co/v0/postings/example?mode=json&skip=100&limit=100"
    )
    job = first.postings[0]
    assert job.title == "Legal adviser"  # Collection never consults candidate preferences.
    assert job.locations == ["London", "Paris"]
    assert "Legal qualification" in job.description and "Flexible hours" in job.description
    assert job.salary["currency"] == "GBP"
    assert "utm_" not in job.url
    assert not decode_page("lever", [lever(), lever()]).complete
    invalid = lever("two")
    invalid["applyUrl"] = "javascript:alert(1)"
    partial = decode_page("lever", [lever(), invalid])
    assert len(partial.postings) == 1 and partial.issues == ["invalid_posting"]
    assert not partial.complete


def test_ashby_publication_locations_salary_and_content_hash() -> None:
    row = {
        "title": "Service designer",
        "isListed": True,
        "jobUrl": "https://jobs.ashbyhq.com/example/design?utm_source=test",
        "applyUrl": "https://jobs.ashbyhq.com/example/design/application",
        "descriptionPlain": "Design public services.",
        "location": "London",
        "secondaryLocations": [{"location": "Dublin"}],
        "workplaceType": "Hybrid",
        "publishedAt": "2026-10-01T10:00:00Z",
        "compensation": {"scrapeableCompensationSalarySummary": "GBP 70K–90K"},
    }
    result = decode_page("ashby", {"apiVersion": "1", "jobs": [row, {"isListed": False}]})
    assert result.complete and len(result.postings) == 1
    job = result.postings[0]
    assert job.external_id == "https://jobs.ashbyhq.com/example/design"
    assert job.locations == ["Dublin", "London"] and job.workplace == "Hybrid"
    assert job.salary == row["compensation"]
    changed = deepcopy(row)
    changed["descriptionPlain"] = "Design education services."
    newer = decode_page("ashby", {"apiVersion": "1", "jobs": [changed]}).postings[0]
    assert job.content_hash() != newer.content_hash()
    assert job.content_hash() == job.model_copy().content_hash()
    assert not decode_page("ashby", {"apiVersion": "2", "jobs": []}).complete
    assert not decode_page("ashby", {"apiVersion": "1", "jobs": [{}]}).complete


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "http://127.0.0.1/jobs",
        "http://[::1]/jobs",
        "https://owner:secret@example.com",
        "https://example.com:55439/jobs",
        "https://machine.local/jobs",
        "https://localhost/jobs",
        "https://host.example.ts.net/",
        "https://example.com/\\evil",
        "https://example.com/\nsecret",
    ],
)
def test_stored_job_links_reject_obviously_unsafe_urls(url: str) -> None:
    with pytest.raises(ValueError):
        public_link(url)


def test_request_construction_rejects_paths_and_preserves_meaningful_query() -> None:
    with pytest.raises(ValueError):
        request_url("greenhouse", "example/../../other")
    with pytest.raises(ValueError):
        request_url("lever", "example", region="internal")
    assert public_link("https://EXAMPLE.com:443/job?id=one&source=two&utm_source=x#detail") == (
        "https://example.com/job?id=one&source=two"
    )
