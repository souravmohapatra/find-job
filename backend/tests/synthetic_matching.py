"""Authored synthetic cases only; these are workflow fixtures, not a matching algorithm."""

import json
from pathlib import Path

from app.ai.matching import PROMPT, task_input
from app.collection.contracts import Posting
from app.domain.matching import Assessment, Reason
from app.domain.profile import Evidence, Facts, Preferences

MODEL = "mock/job-matching-v1"
FACTS = Facts(summary="Synthetic candidate with planning and advisory experience.")
PREFERENCES = Preferences(desired_roles=["Strategy"])
ALTERNATIVE = Preferences(desired_roles=["Legal advice"])
POSTINGS = [
    Posting(
        external_id=slug,
        title=title,
        description=duties,
        url=f"https://jobs.example.com/{slug}",
        apply_url=f"https://jobs.example.com/{slug}/apply",
        locations=["London"],
    )
    for slug, title, duties in [
        ("strategy", "Strategy manager", "Lead strategy and commercial planning."),
        (
            "transfer",
            "Business transformation lead",
            "Plan organisational transformation in a new industry.",
        ),
        ("legal", "Legal adviser", "Provide legal advice and draft contracts."),
    ]
]


def fixtures() -> list[dict]:
    cases = []
    for preferences, decisions in [
        (PREFERENCES, [("aligned", 70), ("adjacent", 30), ("unrelated", 10)]),
        (ALTERNATIVE, [("unrelated", 10), ("unrelated", 10), ("aligned", 65)]),
    ]:
        for posting, (relation, score) in zip(POSTINGS, decisions, strict=True):
            proof = [
                Evidence(span_id="job:description", quote=posting.description),
                Evidence(span_id="preference:desired_roles", quote=preferences.desired_roles[0]),
            ]
            report = Assessment(
                primary_function=posting.title,
                relation=relation,
                function_evidence=proof,
                relevance_score=score,
                score_evidence=proof,
                plausible_connection=relation != "unrelated",
                connection_evidence=proof if relation != "unrelated" else [],
                domain_status="unknown",
                important_unknowns=score == 30,
                reasons=[
                    Reason(
                        text="Synthetic fixture: duties compared with the chosen role family.",
                        evidence=proof,
                    )
                ],
                gaps=[
                    Reason(
                        text="Synthetic fixture: industry experience needs review.", evidence=proof
                    )
                ]
                if score == 30
                else [],
            )
            cases.append(
                {
                    "model": MODEL,
                    "system": PROMPT,
                    "input": task_input(FACTS, preferences, posting),
                    "prompt_version": "matching-v1",
                    "schema_version": "matching-v1",
                    "response": report.model_dump(mode="json"),
                }
            )
    return cases


def write_fixtures(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "job_matching.json").write_text(json.dumps(fixtures(), indent=2) + "\n")
