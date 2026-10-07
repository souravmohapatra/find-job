import json
from datetime import UTC, datetime

import pytest
from app.collection import generic
from app.collection.generic import parse_page

NOW = datetime(2026, 10, 7, 19, tzinfo=UTC)
SOURCE = "https://careers.example.com/jobs/one"


def job(**changes: object) -> dict[str, object]:
    return {
        "@type": "JobPosting",
        "title": "Strategy associate",
        "description": "<p>Develop market plans.</p><script>steal()</script>",
        "hiringOrganization": {"name": "Example Studio", "url": "https://example.com"},
        **changes,
    }


def page(data: object, extra: str = "") -> str:
    return (
        '<script type="application/ld+json">'
        + json.dumps(data).replace("<", "\\u003c")
        + "</script>"
        + extra
    )


def test_detail_metadata_dates_and_remote_locations() -> None:
    parsed = parse_page(
        page(
            job(
                identifier={"@type": "PropertyValue", "value": "R42"},
                datePosted="2026-10-01",
                validThrough="2026-10-07",
                jobLocation=[{"address": {"addressLocality": "London", "addressCountry": "GB"}}],
                jobLocationType="TELECOMMUTE",
                applicantLocationRequirements={"name": "United Kingdom"},
                employmentType=["FULL_TIME", "CONTRACTOR"],
                baseSalary={"currency": "GBP", "value": {"minValue": 50000, "maxValue": 60000}},
            )
        ),
        SOURCE,
        now=NOW,
    )
    found = parsed.candidates[0]
    assert found.posting.url == SOURCE
    assert found.posting.external_id == "R42"
    assert found.posting.description == "Develop market plans."
    assert found.posting.locations == ["London, GB"]
    assert found.applicant_locations == ["United Kingdom"]
    assert found.posting.workplace == "TELECOMMUTE"
    assert found.posting.employment_type == "FULL_TIME, CONTRACTOR"
    assert found.posting.salary and found.posting.salary["currency"] == "GBP"
    assert found.posting.published_at is None
    assert found.advertised_date == "2026-10-01"
    assert found.expired is False
    assert found.employer_name == "Example Studio"
    assert found.employer_url == "https://example.com/"
    assert found.source_url == SOURCE and found.evidence_path == "json_ld[0]"
    assert not parsed.authoritative


def test_graph_references_arrays_and_distinct_functions() -> None:
    data = {
        "@graph": [
            {"@id": "#employer", "@type": "Organization", "name": "Example Studio"},
            job(url="/jobs/one?utm_source=x", hiringOrganization={"@id": "#employer"}),
            {
                "itemListElement": [
                    {
                        "item": job(
                            url="/jobs/legal",
                            title="Legal expert",
                            **{"@type": ["Thing", "https://schema.org/JobPosting"]},
                        )
                    }
                ]
            },
        ]
    }
    parsed = parse_page(page(data), SOURCE, now=NOW)
    assert [x.posting.title for x in parsed.candidates] == ["Strategy associate", "Legal expert"]
    assert parsed.candidates[0].employer_name == "Example Studio"
    assert parsed.candidates[0].posting.url == SOURCE
    assert parsed.candidates[1].evidence_path.endswith("itemListElement[0].item")
    assert not parsed.issues


def test_multiple_jobs_require_unambiguous_urls_and_keep_valid_rows() -> None:
    parsed = parse_page(
        page([job(), job(url="/jobs/two"), job(url="http://127.0.0.1/private")]), SOURCE, now=NOW
    )
    assert len(parsed.candidates) == 1
    assert parsed.candidates[0].posting.url.endswith("/jobs/two")
    assert parsed.issues == ["invalid_job_posting"]


def test_malformed_json_empty_and_script_only_are_not_empty_inventory() -> None:
    parsed = parse_page(
        '<script type="application/ld+json">{broken</script>'
        '<script>fetch("secret")</script><div hidden>private</div>'
        "<template>not visible</template><p>Careers</p>",
        SOURCE,
        now=NOW,
    )
    assert parsed.visible_text == "Careers"
    assert parsed.candidates == []
    assert parsed.issues == ["invalid_json_ld", "no_structured_jobs"]
    assert not parsed.authoritative


def test_links_are_safe_resolved_deduplicated_and_never_follow_base_tag() -> None:
    parsed = parse_page(
        '<base href="http://127.0.0.1/">'
        '<a href="/jobs?page=2" rel="next">Next</a>'
        '<a href="/jobs?page=2&utm_source=x">Duplicate</a>'
        '<a href="javascript:alert(1)">Unsafe</a>'
        '<a href="http://169.254.169.254/">Metadata</a>'
        '<a href="https://jobs.lever.co/example">Board</a>',
        SOURCE,
        now=NOW,
    )
    assert [(x.url, x.relation) for x in parsed.links] == [
        ("https://careers.example.com/jobs?page=2", ["next"]),
        ("https://jobs.lever.co/example", []),
    ]


@pytest.mark.parametrize(
    ("valid", "expected"),
    [
        ("2026-10-06", True),
        ("2026-10-08", False),
        ("2026-10-07T18:00:00Z", True),
        ("2026-10-07T18:00:00", None),
        ("bad", None),
    ],
)
def test_expiry_preserves_evidence_without_claiming_closure(
    valid: str, expected: bool | None
) -> None:
    parsed = parse_page(
        page(job(validThrough=valid, datePosted="2026-10-01T12:00:00+01:00")), SOURCE, now=NOW
    )
    found = parsed.candidates[0]
    assert found.expired is expected
    assert found.valid_through == valid
    assert found.posting.published_at and found.posting.published_at.tzinfo
    assert not parsed.authoritative


def test_conflicting_duplicates_are_visible() -> None:
    parsed = parse_page(
        page([job(url=SOURCE), job(url=SOURCE, title="Different title")]), SOURCE, now=NOW
    )
    assert len(parsed.candidates) == 1
    assert parsed.issues == ["conflicting_job_posting"]


def test_caps_are_explicit_and_missing_fields_do_not_become_jobs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(generic, "MAX_VISIBLE", 5)
    monkeypatch.setattr(generic, "MAX_LINKS", 1)
    parsed = parse_page(
        page(job(description=""), '<p>Long description</p><a href="/a">A</a><a href="/b">B</a>'),
        SOURCE,
        now=NOW,
    )
    assert not parsed.candidates
    assert len(parsed.visible_text) == 5 and len(parsed.links) == 1
    assert parsed.issues == ["invalid_job_posting", "link_limit", "visible_text_limit"]
    monkeypatch.setattr(generic, "MAX_NODES", 2)
    parsed = parse_page(page({"@graph": [job(url="/a"), job(url="/b")]}), SOURCE, now=NOW)
    assert "structured_data_limit" in parsed.issues
    monkeypatch.setattr(generic, "MAX_HTML", 5)
    assert parse_page("too large", SOURCE, now=NOW).issues == ["html_limit"]
