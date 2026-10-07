from uuid import uuid4

import pytest
from app.ai import matching
from app.collection.contracts import Posting
from app.domain.matching import Assessment, CriterionResult, category, validate
from app.domain.profile import Criterion, Evidence, Fact, Facts, Preferences

FACTS = Facts(summary="Led strategy projects and financial planning.")
PREFS = Preferences(desired_roles=["Strategy"], domains=["Entertainment"])
JOB = Posting(
    external_id="one",
    title="Commercial strategy",
    url="https://example.com/jobs/one",
    apply_url="https://example.com/jobs/one",
    description="Lead strategy in a new domain. Based in Berlin. Finance sector.",
)


def citation(span: str, quote: str) -> Evidence:
    return Evidence(span_id=span, quote=quote)


def assessment(**changes) -> Assessment:
    evidence = [
        citation("job:description", "Lead strategy"),
        citation("preference:desired_roles", "Strategy"),
    ]
    return Assessment(
        primary_function="Commercial planning",
        relation="adjacent",
        function_evidence=evidence,
        relevance_score=30,
        score_evidence=evidence,
        plausible_connection=True,
        connection_evidence=evidence,
        domain_status="unknown",
        important_unknowns=False,
        **changes,
    )


def decide(result, preferences=PREFS):
    validate(result, preferences, matching.evidence(FACTS, preferences, JOB))
    return category(result, preferences)


def test_wide_net_threshold_and_uncertainty_do_not_require_high_precision():
    base = assessment()
    assert decide(base) == "possible_match"
    assert decide(base.model_copy(update={"relevance_score": 29})) == "not_match"
    assert decide(base.model_copy(update={"relevance_score": 60})) == "match"
    assert (
        decide(base.model_copy(update={"relevance_score": 95, "important_unknowns": True}))
        == "possible_match"
    )
    assert (
        decide(base.model_copy(update={"relation": "unclear", "relevance_score": None}))
        == "possible_match"
    )
    with pytest.raises(ValueError):
        decide(
            base.model_copy(
                update={
                    "relation": "unclear",
                    "relevance_score": None,
                    "plausible_connection": False,
                }
            )
        )


def test_unrelated_function_overrides_high_score_without_global_title_blacklist():
    # The relation is model evidence about this profile, never a hardcoded occupation list.
    for role in ["Legal expert", "Data analyst", "Strategy director"]:
        result = assessment().model_copy(
            update={"primary_function": role, "relation": "unrelated", "relevance_score": 99}
        )
        assert decide(result) == "not_match"
    legal_preferences = Preferences(desired_roles=["Legal advice"])
    legal_job = JOB.model_copy(
        update={"title": "Legal expert", "description": "Provide legal advice."}
    )
    proof = [
        citation("job:description", "Provide legal advice"),
        citation("preference:desired_roles", "Legal advice"),
    ]
    result = assessment().model_copy(
        update={
            "primary_function": "Legal advice",
            "relation": "aligned",
            "relevance_score": 80,
            "function_evidence": proof,
            "score_evidence": proof,
            "connection_evidence": proof,
        }
    )
    validate(result, legal_preferences, matching.evidence(FACTS, legal_preferences, legal_job))
    assert category(result, legal_preferences) == "match"


def test_only_explicit_required_criteria_or_domain_focus_can_reject():
    criterion = Criterion(id=uuid4(), kind="location", description="London", strength="preferred")
    preferences = Preferences(desired_roles=["Strategy"], criteria=[criterion])
    report = CriterionResult(
        preference_id=criterion.id,
        status="not_met",
        explanation="Listing states another location",
        comparable=True,
        evidence=[
            citation("job:description", "Berlin"),
            citation(f"preference:{criterion.id}", "London"),
        ],
    )
    result = assessment(criteria=[report])
    assert decide(result, preferences) == "possible_match"
    preferences.criteria[0].strength = "required"
    assert decide(result, preferences) == "not_match"
    report.status = "unknown"
    result.criteria = [report]
    result.relevance_score = 80
    assert decide(result, preferences) == "possible_match"
    for mode in ["open", "expand"]:
        assert (
            decide(
                assessment().model_copy(update={"domain_status": "not_met"}),
                PREFS.model_copy(update={"domain_mode": mode}),
            )
            == "possible_match"
        )
    focus = PREFS.model_copy(update={"domain_mode": "focus"})
    assert (
        decide(assessment().model_copy(update={"relevance_score": 80}), focus) == "possible_match"
    )
    conflict = assessment().model_copy(
        update={
            "domain_status": "not_met",
            "domain_evidence": [
                citation("job:description", "Finance sector"),
                citation("preference:domains", "Entertainment"),
            ],
        }
    )
    assert decide(conflict, focus) == "not_match"


def test_unknown_or_incomparable_salary_cannot_be_reported_as_conflict():
    criterion = Criterion(
        id=uuid4(), kind="compensation", description="GBP 60000 yearly", strength="required"
    )
    preferences = PREFS.model_copy(update={"criteria": [criterion]})
    report = CriterionResult(
        preference_id=criterion.id,
        status="not_met",
        explanation="Currency/period unknown",
        comparable=False,
        evidence=[
            citation("job:description", "Lead strategy"),
            citation(f"preference:{criterion.id}", "GBP 60000 yearly"),
        ],
    )
    with pytest.raises(ValueError):
        decide(assessment(criteria=[report]), preferences)
    report.status = "unknown"
    assert decide(assessment(criteria=[report]), preferences) == "possible_match"
    with pytest.raises(ValueError):
        decide(assessment(), preferences)
    with pytest.raises(ValueError):
        decide(assessment(criteria=[report, report]), preferences)


def test_fabricated_evidence_is_an_error_not_a_speculative_shortlist():
    result = assessment().model_copy(
        update={"function_evidence": [citation("job:description", "Invented duty")]}
    )
    with pytest.raises(ValueError):
        decide(result)


def test_matching_payload_omits_original_cv_evidence_and_redacts_contacts(monkeypatch):
    facts = FACTS.model_copy(
        update={
            "summary": "Led strategy. Email person@example.invalid",
            "skills": [
                Fact(value="Planning", evidence=[citation("cv-private", "Private CV quotation")])
            ],
        }
    )

    def infer(task, config, operation, system, payload, model, check, **versions):
        assert task == "job_matching" and "untrusted data" in system
        serialized = str(payload)
        assert (
            "Private CV quotation" not in serialized and "person@example.invalid" not in serialized
        )
        assert "[email removed]" in serialized
        assert versions["prompt_version"] == "matching-v1"
        result = assessment()
        check(result)
        return result

    monkeypatch.setattr(matching, "infer", infer)
    assert matching.assess(facts, PREFS, JOB, uuid4(), uuid4()).relevance_score == 30


def test_title_only_function_evidence_cannot_override_cited_duties():
    result = assessment().model_copy(
        update={
            "function_evidence": [
                citation("job:title", "Commercial strategy"),
                citation("preference:desired_roles", "Strategy"),
            ]
        }
    )
    with pytest.raises(ValueError):
        decide(result)


def test_profile_uncertainty_and_conservative_experience_are_preserved():
    facts = Facts(
        summary="Professional profile", skills=[Fact(value="Planning", origin="inferred")]
    )
    spans = {span.id: span.text for span in matching.evidence(facts, PREFS, JOB)}
    assert '"origin": "inferred"' in spans["profile:skills"]
    assert '"maximum_years": null' in spans["profile:experience"]
    assert '"basis": "incomplete_dates"' in spans["profile:experience"]
