from uuid import uuid4

import pytest
from app.ai import extraction
from app.ai.extraction import ExtractedJob, Extraction, context, posting, validate
from app.collection.generic import PageLink
from app.domain.profile import Evidence
from app.services.operations import OperationError

TEXT = "Example Studio is hiring. Strategy manager. Develop market plans. London. Full time."
URL = "https://example.com/jobs/one"


def job(**changes):
    return ExtractedJob(
        title=Evidence(span_id="s1", quote="Strategy manager"),
        employer=Evidence(span_id="s1", quote="Example Studio"),
        description=[Evidence(span_id="s1", quote="Develop market plans.")],
        vacancy_evidence=[Evidence(span_id="s1", quote="is hiring")],
        locations=[Evidence(span_id="s1", quote="London")],
        employment_type=Evidence(span_id="s1", quote="Full time"),
        link_id="source",
        status="open",
    ).model_copy(update=changes)


def test_grounded_extraction_uses_independent_task_and_no_profile_payload(monkeypatch):
    configuration, operation = uuid4(), uuid4()

    def infer(task, config_id, operation_id, system, payload, output, validator, **versions):
        assert task == "job_extraction" and config_id == configuration and operation_id == operation
        assert "untrusted data" in system
        assert set(payload) == {"spans", "links"}
        assert output is Extraction and versions["prompt_version"] == "job-extraction-v1"
        result = Extraction(jobs=[job()], coverage="detail")
        validator(result)
        return result

    monkeypatch.setattr(extraction, "infer", infer)
    result = extraction.extract(TEXT, URL, [], configuration, operation)
    spans, urls = context(TEXT, URL, [])
    validate(result, spans, urls)
    normalized = posting(result.jobs[0], urls)
    assert normalized.title == "Strategy manager" and normalized.locations == ["London"]
    assert normalized.description == "Develop market plans."
    assert normalized.published_at is None and normalized.salary is None


@pytest.mark.parametrize(
    "changed",
    [
        {"employer": Evidence(span_id="s1", quote="Invented employer")},
        {"title": Evidence(span_id="missing", quote="Strategy manager")},
        {"link_id": "https://evil.example/"},
    ],
)
def test_unsupported_claims_and_model_generated_urls_are_rejected(changed):
    spans, urls = context(TEXT, URL, [])
    with pytest.raises(ValueError):
        validate(Extraction(jobs=[job(**changed)], coverage="detail"), spans, urls)


def test_multiple_roles_need_distinct_observed_links_and_non_job_pages_cannot_claim_jobs():
    spans, urls = context(
        TEXT, URL, [PageLink(url="https://example.com/jobs/two", label="Role two")]
    )
    with pytest.raises(ValueError):
        validate(Extraction(jobs=[job(), job(link_id="l1")], coverage="listing"), spans, urls)
    with pytest.raises(ValueError):
        validate(Extraction(jobs=[job()], coverage="not_a_job_page"), spans, urls)
    validate(Extraction(jobs=[], coverage="not_a_job_page"), spans, urls)


def test_closed_or_uncertain_evidence_is_retained_without_inventing_open_status():
    spans, urls = context(TEXT, URL, [])
    result = Extraction(jobs=[job(status="uncertain")], coverage="uncertain")
    validate(result, spans, urls)
    assert result.jobs[0].status == "uncertain"


def test_input_limits_do_not_silently_truncate_and_unsafe_links_are_rejected():
    with pytest.raises(OperationError):
        context("x" * 40001, URL, [])
    with pytest.raises(ValueError):
        context(TEXT, URL, [PageLink(url="http://127.0.0.1/", label="Private")])
