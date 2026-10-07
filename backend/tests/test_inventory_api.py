from uuid import UUID

from app.collection.contracts import InventoryPage
from app.collection.models import CollectionRun, Company, Job
from app.db import get_engine
from app.profile_models import Operation
from app.services.operations import process_operation
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_inventory import collect, posting, source


def auth(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={
            "username": "owner",
            "password": "synthetic-test-password",
        },
        headers={"Origin": "https://testserver"},
    )
    assert response.status_code == 200
    return {"Origin": "https://testserver", "X-CSRF-Token": response.json()["csrf_token"]}


def test_company_creation_is_authenticated_idempotent_and_keeps_unresolved_watch(client):
    assert client.get("/api/v1/companies").status_code == 401
    headers = auth(client) | {"Idempotency-Key": "synthetic-company"}
    body = {"label": "Example Entertainment", "interval_hours": 12}
    created = client.post("/api/v1/companies", headers=headers, json=body)
    assert created.status_code == 202
    again = client.post("/api/v1/companies", headers=headers, json=body)
    assert again.json() == created.json()
    assert (
        client.post(
            "/api/v1/companies", headers=headers, json={"label": "Different company"}
        ).status_code
        == 409
    )
    identifier = created.json()["resource_id"]
    assert client.get("/api/v1/companies").json()["items"][0]["resolution"] == "unresolved"
    process_operation(UUID(created.json()["operation_id"]))
    assert client.get(f"/api/v1/companies/{identifier}").status_code == 200
    changed = client.patch(
        f"/api/v1/companies/{identifier}",
        headers=headers | {"If-Match": '"1"'},
        json=body | {"paused": True},
    )
    assert changed.status_code == 200 and changed.json()["revision"] == 2
    assert (
        client.patch(
            f"/api/v1/companies/{identifier}", headers=headers | {"If-Match": '"1"'}, json=body
        ).status_code
        == 409
    )
    assert client.post(f"/api/v1/companies/{identifier}/check", headers=headers).status_code == 409
    with Session(get_engine()) as db:
        assert db.scalar(select(func.count()).select_from(Company)) == 1


def test_sources_require_owner_confirmation_and_manual_checks_join_existing_work(client):
    headers = auth(client)
    created = client.post("/api/v1/companies", headers=headers, json={"label": "Example"}).json()
    identifier = created["resource_id"]
    path = f"/api/v1/companies/{identifier}/sources"
    body = {"adapter": "lever", "board": "example", "region": "eu"}
    assert client.post(path, headers=headers, json=body).status_code == 422
    body["confirmed_company"] = True
    result = client.post(path, headers=headers, json=body)
    assert result.status_code == 201
    source_id = result.json()["id"]
    assert client.post(path, headers=headers, json=body).json()["id"] == source_id
    assert "api.eu.lever.co" in result.json()["url"]
    assert result.json()["last_success_at"] is None
    pending = client.post(f"/api/v1/companies/{identifier}/check", headers=headers)
    assert pending.status_code == 202
    assert (
        client.post(f"/api/v1/companies/{identifier}/check", headers=headers).json()
        == pending.json()
    )
    process_operation(UUID(pending.json()["operation_id"]))
    with Session(get_engine()) as db:
        assert db.scalar(select(func.count()).select_from(CollectionRun)) == 1
        assert db.scalar(select(Operation).where(Operation.kind == "source_collect")) is not None
    paused = client.patch(
        f"/api/v1/companies/{identifier}",
        headers=headers | {"If-Match": '"1"'},
        json={"label": "Example", "paused": True},
    )
    assert paused.status_code == 200
    view = client.get(path).json()[0]
    assert view["revision"] == 2  # Pause invalidates already-dispatched results.
    assert (
        client.patch(
            f"/api/v1/sources/{source_id}",
            headers=headers | {"If-Match": '"1"'},
            json={"enabled": False, "interval_hours": 12},
        ).status_code
        == 409
    )
    assert client.get(f"/api/v1/sources/{source_id}/runs").json()[0]["state"] == "collecting"


def test_all_jobs_includes_unassessed_roles_and_cursor_search_filters(client):
    with Session(get_engine()) as db, db.begin():
        row = source(db)
        company_id = row.company_id
        collect(
            db,
            row,
            InventoryPage(
                postings=[
                    posting("a"),
                    posting("b").model_copy(update={"title": "Legal adviser"}),
                    posting("c"),
                ],
                complete=True,
            ),
        )
        # Distinguish availability from suitability.
        db.scalar(select(Job).order_by(Job.id)).availability = "closed"
    assert client.get("/api/v1/jobs?view=all").status_code == 401
    auth(client)
    assert client.get("/api/v1/jobs").json()["code"] == "matching_unavailable"
    path = f"/api/v1/jobs?view=all&availability=all&company_id={company_id}&limit=2"
    first = client.get(path)
    assert first.status_code == 200
    page = first.json()
    assert len(page["items"]) == 2 and page["next_cursor"]
    second = client.get(path + "&cursor=" + page["next_cursor"]).json()
    assert len(second["items"]) == 1 and second["next_cursor"] is None
    items = page["items"] + second["items"]
    assert len({item["id"] for item in items}) == 3
    assert all(item["assessment_status"] == "not_assessed" for item in items)
    assert any(item["posting"]["title"] == "Legal adviser" for item in items)
    assert (
        client.get("/api/v1/jobs?view=all&availability=all&q=Legal").json()["items"][0]["posting"][
            "title"
        ]
        == "Legal adviser"
    )
    assert client.get("/api/v1/jobs?view=all&availability=all&q=Example").status_code == 200
    assert (
        client.get(
            "/api/v1/jobs", params={"view": "all", "cursor": page["next_cursor"]}
        ).status_code
        == 422
    )
    detail = client.get(f"/api/v1/jobs/{items[0]['id']}").json()
    assert detail["sources"][0]["company_id"] == str(company_id) and detail["revision_count"] == 1
    assert len(client.get("/api/v1/jobs?view=all").json()["items"]) == 2
    assert client.get("/api/v1/jobs?view=all&cursor=bad-base64").status_code == 422


def test_invalid_source_urls_and_intervals_do_not_create_watches(client):
    headers = auth(client)
    for body in [
        {"label": " "},
        {"label": "Example", "website": "http://127.0.0.1"},
        {"label": "Example", "interval_hours": 0},
        {"label": "Example", "interval_hours": 721},
    ]:
        assert client.post("/api/v1/companies", headers=headers, json=body).status_code == 422
    assert client.get("/api/v1/companies").json()["items"] == []


def test_manual_check_key_cannot_be_reused_for_another_company_with_pending_work(client):
    headers = auth(client)
    ids = [
        client.post("/api/v1/companies", headers=headers, json={"label": label}).json()[
            "resource_id"
        ]
        for label in ["First company", "Second company"]
    ]
    keyed = headers | {"Idempotency-Key": "same-manual-key"}
    first = client.post(f"/api/v1/companies/{ids[0]}/check", headers=keyed)
    assert first.status_code == 202
    assert client.post(f"/api/v1/companies/{ids[1]}/check", headers=headers).status_code == 202
    assert client.post(f"/api/v1/companies/{ids[1]}/check", headers=keyed).status_code == 409
    assert client.post(f"/api/v1/companies/{ids[0]}/check", headers=keyed).json() == first.json()


def test_default_availability_includes_unknown_and_keeps_explicit_filters(client):
    with Session(get_engine()) as db, db.begin():
        row = source(db)
        collect(
            db,
            row,
            InventoryPage(postings=[posting("a"), posting("b"), posting("c")], complete=True),
        )
        jobs = list(db.scalars(select(Job).order_by(Job.id)))
        jobs[0].availability = "unknown"
        jobs[1].availability = "closed"
    auth(client)
    result = client.get("/api/v1/jobs?view=all").json()["items"]
    assert {job["availability"] for job in result} == {"active", "unknown"}
    assert len(client.get("/api/v1/jobs?view=all&availability=active").json()["items"]) == 1
    assert len(client.get("/api/v1/jobs?view=all&availability=all").json()["items"]) == 3


def test_saved_but_unmapped_matching_model_is_unavailable_without_hiding_inventory(client):
    from app.ai.contracts import TaskConfig
    from app.ai.models import TaskRevision
    from test_assessments import setup

    with Session(get_engine()) as db, db.begin():
        setup(db)
        db.add(
            TaskRevision(
                task="job_matching", revision=2, config=TaskConfig().model_dump(mode="json")
            )
        )
        job_id = db.scalar(select(Job.id))
    headers = auth(client)
    response = client.get("/api/v1/jobs")
    assert response.status_code == 503 and response.json()["code"] == "matching_unavailable"
    all_jobs = client.get("/api/v1/jobs?view=all").json()
    assert not all_jobs["matching_available"] and len(all_jobs["items"]) == 1
    result = client.post(f"/api/v1/jobs/{job_id}/reassess", headers=headers)
    assert result.status_code == 409 and result.json()["code"] == "matching_unavailable"
