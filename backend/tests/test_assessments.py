import pytest
from app.ai.contracts import TaskConfig
from app.ai.models import TaskRevision
from app.collection.models import Job, JobAssessment, JobRevision
from app.config import get_settings
from app.db import get_engine
from app.domain.matching import POLICY_VERSION
from app.domain.profile import Facts, Preferences
from app.profile_models import Operation, Profile, ProfileRevision
from app.services import matching
from app.services.operations import create_operation, process_operation
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_inventory import collect, posting, source
from test_matching import assessment


def setup(db):
    from app.collection.contracts import InventoryPage

    db.add(Profile(id=1, current_revision=1))
    db.flush()
    profile = ProfileRevision(
        revision=1,
        facts=Facts(summary="Strategy planning").model_dump(),
        preferences=Preferences(desired_roles=["Strategy"]).model_dump(mode="json"),
    )
    config = TaskRevision(
        task="job_matching",
        revision=1,
        config=TaskConfig(model="example/matching").model_dump(mode="json"),
    )
    db.add_all([profile, config])
    db.flush()
    row = source(db)
    collect(db, row, InventoryPage(postings=[posting(description="Lead strategy")], complete=True))
    operation = db.scalar(select(Operation).where(Operation.kind == "job_assess"))
    return profile.id, config.id, operation.id


def test_worker_persists_versioned_result_replay_and_historical_completion(monkeypatch):
    calls = []

    def fake(*args):
        calls.append(True)
        # Profile changes while inference is in flight; captured result must stay historical.
        with Session(get_engine()) as db, db.begin():
            db.get(Profile, 1).current_revision = 2
            db.add(
                ProfileRevision(
                    revision=2,
                    facts=Facts(summary="Changed preference").model_dump(),
                    preferences=Preferences(desired_roles=["Teaching"]).model_dump(mode="json"),
                )
            )
        return assessment()

    monkeypatch.setattr(matching, "assess", fake)
    with Session(get_engine()) as db, db.begin():
        profile_id, config_id, identifier = setup(db)
    process_operation(identifier)
    process_operation(identifier)
    with Session(get_engine()) as db:
        result = db.scalar(select(JobAssessment))
        assert result.profile_revision_id == profile_id and result.config_id == config_id
        assert result.policy_version == POLICY_VERSION and result.category == "possible_match"
        assert db.get(Profile, 1).current_revision == 2
        assert matching.current(db, result.job_revision_id) is None
        assert db.get(Operation, identifier).state == "succeeded"
    assert calls == [True]


def test_reassessment_batches_join_existing_snapshot_intents(monkeypatch):
    monkeypatch.setattr(matching, "assess", lambda *args: assessment())
    with Session(get_engine()) as db, db.begin():
        profile_id, config_id, _ = setup(db)
        first = db.scalar(select(Job))
        other = Job(company_id=first.company_id, canonical_key="b" * 64)
        db.add(other)
        db.flush()
        db.add(
            JobRevision(
                job_id=other.id,
                revision=1,
                content_hash="c" * 64,
                posting=posting("other", description="Lead strategy").model_dump(mode="json"),
                source_id=db.scalar(select(JobRevision)).source_id,
            )
        )
        db.flush()
        assert matching.expand(db, {"profile_revision_id": str(profile_id)}, batch_size=1) == 1
        assert matching.expand(db, {"profile_revision_id": str(profile_id)}, batch_size=1) == 1
        continuation = db.scalar(select(Operation).where(Operation.kind == "profile_reassess"))
        continuation_id = continuation.id
        assert continuation.parameters["ai_config_id"] == str(config_id)
    process_operation(continuation_id)
    with Session(get_engine()) as db:
        operations = list(db.scalars(select(Operation).where(Operation.kind == "job_assess")))
        assert len(operations) == 2
        identifiers = [operation.id for operation in operations]
    for identifier in identifiers:
        process_operation(identifier)
    with Session(get_engine()) as db:
        assert db.scalar(select(func.count()).select_from(JobAssessment)) == 2


def test_mode_change_does_not_publish_or_call_live(monkeypatch):
    with Session(get_engine()) as db, db.begin():
        _, _, identifier = setup(db)
    monkeypatch.setattr(get_settings(), "integration_mode", "live")
    monkeypatch.setattr(
        matching, "assess", lambda *args: pytest.fail("Must not send queued mock data live")
    )
    process_operation(identifier)
    with Session(get_engine()) as db:
        assert db.get(Operation, identifier).error_code == "assessment_mode_changed"
        assert db.scalar(select(JobAssessment)) is None


def test_profile_purge_removes_explanations_and_cancels_assessment_work(monkeypatch, client):
    from test_inventory_api import auth

    monkeypatch.setattr(matching, "assess", lambda *args: assessment())
    with Session(get_engine()) as db, db.begin():
        _, _, identifier = setup(db)
    process_operation(identifier)
    with Session(get_engine()) as db, db.begin():
        pending = create_operation(
            db, "job_assess", "synthetic-pending", {"profile_revision_id": "synthetic"}
        )
        pending_id = pending.id
    headers = auth(client)
    response = client.post(
        "/api/v1/profile/purge", headers=headers, json={"confirmation": "DELETE PROFILE"}
    )
    assert response.status_code == 204
    with Session(get_engine()) as db:
        assert db.scalar(select(JobAssessment)) is None
        assert db.get(Operation, pending_id).state == "cancelled"
        assert db.scalar(select(Job)) is not None


def test_lost_worker_lease_cannot_publish_assessment(monkeypatch):
    from uuid import uuid4

    with Session(get_engine()) as db, db.begin():
        _, _, identifier = setup(db)

    def lose_lease(*args):
        with Session(get_engine()) as db, db.begin():
            db.get(Operation, identifier).lease_token = uuid4()
        return assessment()

    monkeypatch.setattr(matching, "assess", lose_lease)
    process_operation(identifier)
    with Session(get_engine()) as db:
        assert db.scalar(select(JobAssessment)) is None


def test_purge_during_inference_discards_returned_explanation(monkeypatch, client):
    from test_inventory_api import auth

    headers = auth(client)
    with Session(get_engine()) as db, db.begin():
        _, _, identifier = setup(db)

    def purge(*args):
        assert (
            client.post(
                "/api/v1/profile/purge", headers=headers, json={"confirmation": "DELETE PROFILE"}
            ).status_code
            == 204
        )
        return assessment()

    monkeypatch.setattr(matching, "assess", purge)
    process_operation(identifier)
    with Session(get_engine()) as db:
        assert db.scalar(select(JobAssessment)) is None
        assert db.get(Operation, identifier).state == "cancelled"


def test_current_assessment_requires_current_configuration(monkeypatch):
    monkeypatch.setattr(matching, "assess", lambda *args: assessment())
    with Session(get_engine()) as db, db.begin():
        _, _, identifier = setup(db)
    process_operation(identifier)
    with Session(get_engine()) as db, db.begin():
        revision = db.scalar(select(JobRevision))
        assert matching.current(db, revision.id) is not None
        db.add(
            TaskRevision(
                task="job_matching",
                revision=2,
                config=TaskConfig(model="example/other").model_dump(mode="json"),
            )
        )
        db.flush()
        assert matching.current(db, revision.id) is None


@pytest.mark.parametrize(
    "score,expected,included",
    [(30, "possible_match", True), (70, "match", True), (20, "not_match", False)],
)
def test_shortlist_api_uses_current_categories_and_keeps_all_jobs(
    monkeypatch, client, score, expected, included
):
    from test_inventory_api import auth

    monkeypatch.setattr(
        matching, "assess", lambda *args: assessment().model_copy(update={"relevance_score": score})
    )
    with Session(get_engine()) as db, db.begin():
        _, _, identifier = setup(db)
    process_operation(identifier)
    auth(client)
    shortlist = client.get("/api/v1/jobs").json()
    assert shortlist["matching_available"] is True
    assert len(shortlist["items"]) == int(included)
    all_jobs = client.get("/api/v1/jobs?view=all").json()["items"]
    assert len(all_jobs) == 1
    item = all_jobs[0]
    assert item["assessment_status"] == "assessed"
    assert item["assessment"]["category"] == expected
    assert item["assessment"]["integration_mode"] == "mock"
    detail = client.get(f"/api/v1/jobs/{item['id']}").json()
    assert detail["assessment"]["report"]["function_evidence"]
    assert detail["assessment_operation"]["state"] == "succeeded"


def test_api_stale_assessment_and_current_failure_are_not_rejections(monkeypatch, client):
    from app.services.operations import OperationError
    from test_inventory_api import auth

    monkeypatch.setattr(matching, "assess", lambda *args: assessment())
    with Session(get_engine()) as db, db.begin():
        _, _, identifier = setup(db)
    process_operation(identifier)
    auth(client)
    with Session(get_engine()) as db, db.begin():
        db.add(
            TaskRevision(
                task="job_matching",
                revision=2,
                config=TaskConfig(model="example/new").model_dump(mode="json"),
            )
        )
        db.flush()
        matching.expand(db, {})
        pending = db.scalar(
            select(Operation).where(Operation.kind == "job_assess", Operation.id != identifier)
        ).id
    assert client.get("/api/v1/jobs").json()["items"] == []
    item = client.get("/api/v1/jobs?view=all").json()["items"][0]
    assert item["assessment_status"] == "stale" and item["assessment"] is None
    assert item["assessment_operation"]["state"] == "queued"

    def fail(*args):
        raise OperationError("synthetic_failure", "Synthetic provider failure")

    monkeypatch.setattr(matching, "assess", fail)
    process_operation(pending)
    item = client.get("/api/v1/jobs?view=all").json()["items"][0]
    assert item["assessment"] is None
    assert item["assessment_operation"]["state"] == "failed"
    assert item["assessment_operation"]["error_code"] == "synthetic_failure"


def test_new_job_revision_invalidates_shortlist_result(monkeypatch, client):
    from test_inventory_api import auth

    monkeypatch.setattr(matching, "assess", lambda *args: assessment())
    with Session(get_engine()) as db, db.begin():
        _, _, identifier = setup(db)
    process_operation(identifier)
    auth(client)
    with Session(get_engine()) as db, db.begin():
        prior = db.scalar(select(JobRevision))
        db.get(Job, prior.job_id).current_revision = 2
        db.add(
            JobRevision(
                job_id=prior.job_id,
                revision=2,
                content_hash="f" * 64,
                posting=prior.posting,
                source_id=prior.source_id,
            )
        )
    assert client.get("/api/v1/jobs").json()["items"] == []
    item = client.get("/api/v1/jobs?view=all").json()["items"][0]
    assert item["assessment_status"] == "stale"
    assert item["assessment"] is None and item["assessment_operation"] is None


def test_mode_change_needs_new_result_and_distinct_intent(monkeypatch, client):
    from test_inventory_api import auth

    monkeypatch.setattr(matching, "assess", lambda *args: assessment())
    with Session(get_engine()) as db, db.begin():
        _, _, identifier = setup(db)
    process_operation(identifier)
    auth(client)
    monkeypatch.setattr(get_settings(), "integration_mode", "live")
    assert client.get("/api/v1/jobs").json()["items"] == []
    with Session(get_engine()) as db, db.begin():
        assert matching.current(db, db.scalar(select(JobRevision.id))) is None
        matching.expand(db, {"integration_mode": "live"})
        live = db.scalar(
            select(Operation).where(Operation.kind == "job_assess", Operation.id != identifier)
        ).id
    # Mock the task boundary; no actual live provider is invoked.
    process_operation(live)
    result = client.get("/api/v1/jobs").json()["items"][0]
    assert result["assessment"]["integration_mode"] == "live"
    with Session(get_engine()) as db:
        assert db.scalar(select(func.count()).select_from(JobAssessment)) == 2
