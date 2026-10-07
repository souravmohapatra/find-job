"""Populate synthetic discovery evidence in the fixed disposable browser database only."""

import sys
from pathlib import Path
from uuid import UUID

from sqlalchemy import URL, create_engine, select
from sqlalchemy.orm import Session

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "backend"))
from app.collection.models import Company, DiscoveryRun  # noqa: E402
from app.profile_models import Operation, now  # noqa: E402

engine = create_engine(
    URL.create(
        "postgresql+psycopg",
        username="jobfinder",
        password=(root / ".secrets/test_db_password").read_text().strip(),
        host="127.0.0.1",
        port=55439,
        database="jobfinder_test_browser",
    ),
    hide_parameters=True,
    connect_args={"connect_timeout": 5},
)
with Session(engine) as db, db.begin():
    company = db.get(Company, UUID(sys.argv[1]), with_for_update=True)
    if company is None or company.label != "Synthetic Discovery":
        raise SystemExit("The synthetic browser company is required.")
    for operation in db.scalars(
        select(Operation).where(
            Operation.kind == "company_discover",
            Operation.parameters["company_id"].astext == str(company.id),
            Operation.state.in_(["queued", "running"]),
        )
    ):
        operation.state = "cancelled"
        operation.lease_token = None
    for run in db.scalars(select(DiscoveryRun).where(DiscoveryRun.company_id == company.id)):
        if run.state == "running":
            run.state = "cancelled"
            run.finished_at = now()
    company.resolution = "needs_review"
    db.add(
        DiscoveryRun(
            company_id=company.id,
            company_revision=company.revision,
            state="partial",
            cursor=1,
            frontier=[],
            issues=["search_candidates_unverified"],
            candidates=[
                {
                    "url": "https://example.com/careers",
                    "title": "Synthetic careers",
                    "employer": None,
                    "source_url": "https://example.com/careers",
                    "evidence_path": "synthetic.brave.result",
                    "status": "needs_identity_review",
                }
            ],
            finished_at=now(),
        )
    )
engine.dispose()
