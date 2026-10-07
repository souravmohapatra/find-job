from datetime import timedelta

from app.collection.contracts import InventoryPage
from app.collection.models import Company, Job
from app.db import get_engine
from app.profile_models import now
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_inventory import collect, posting, source
from test_inventory_api import auth


def test_summary_deduplicates_jobs_and_distinguishes_source_gaps(client):
    instant = now()
    with Session(get_engine()) as db, db.begin():
        first = source(db)
        company_id = first.company_id
        collect(db, first, InventoryPage(postings=[posting(), posting("b")], complete=True))
        second = source(db, company_id=company_id, board="other")
        second.authoritative = False
        collect(db, second, InventoryPage(postings=[posting()], complete=False))
        third = source(db, company_id=company_id, board="disabled")
        third.enabled = False
        third.last_error = "disabled_error"
        third.next_due_at = instant - timedelta(days=1)
        first.next_due_at = instant
        first.cooldown_until = instant + timedelta(hours=4)
        second.next_due_at = instant + timedelta(hours=2)
        job = db.scalar(select(Job).where(Job.company_id == company_id))
        job.availability = "unknown"
        expected_success = first.last_success_at.isoformat()
    auth(client)
    detail = client.get(f"/api/v1/companies/{company_id}").json()
    summary = detail["coverage"]
    assert summary["collected_jobs"] == 2  # The same vacancy occurs in two sources.
    assert summary["active_jobs"] == summary["unknown_jobs"] == 1
    assert summary["closed_jobs"] == 0
    assert summary["sources"] == 3 and summary["enabled_sources"] == 2
    assert summary["partial_sources"] == summary["sources_needing_attention"] == 1
    assert summary["sources_without_success"] == 1
    assert summary["last_success_at"].replace("Z", "+00:00") == expected_success
    assert summary["last_attempt_at"] is not None
    assert (
        summary["next_check_at"].replace("Z", "+00:00")
        == (instant + timedelta(hours=2)).isoformat()
    )
    listed = client.get("/api/v1/companies").json()["items"][0]
    assert listed["coverage"] == summary


def test_no_sources_disabled_and_paused_are_distinct_without_false_dates(client):
    with Session(get_engine()) as db, db.begin():
        company = Company(label="Unresolved watch")
        db.add(company)
        db.flush()
        company_id = company.id
    headers = auth(client)
    path = f"/api/v1/companies/{company_id}"
    summary = client.get(path).json()["coverage"]
    assert summary["collected_jobs"] == summary["sources"] == 0
    assert summary["last_success_at"] is None and summary["next_check_at"] is None
    assert summary["next_discovery_at"] is not None
    with Session(get_engine()) as db, db.begin():
        row = source(db, company_id=company_id)
        row.enabled = False
    summary = client.get(path).json()["coverage"]
    assert summary["sources"] == 1 and summary["enabled_sources"] == 0
    assert summary["next_check_at"] is None
    changed = client.patch(
        path,
        headers=headers | {"If-Match": '"1"'},
        json={
            "label": "Unresolved watch",
            "paused": True,
        },
    )
    assert changed.status_code == 200
    summary = changed.json()["coverage"]
    assert summary["next_check_at"] is None and summary["next_discovery_at"] is None
