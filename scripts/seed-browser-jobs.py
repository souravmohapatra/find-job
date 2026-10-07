"""Populate synthetic inventory in the fixed disposable browser database only."""

import sys
from pathlib import Path
from uuid import UUID

from sqlalchemy import URL, create_engine, select
from sqlalchemy.orm import Session

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "backend"))
from app.collection.contracts import InventoryPage, Posting  # noqa: E402
from app.collection.inventory import apply_page, begin_run  # noqa: E402
from app.collection.models import Company, Source  # noqa: E402
from app.profile_models import now  # noqa: E402

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
    company = db.get(Company, UUID(sys.argv[1]))
    if company is None or company.label != "Synthetic Entertainment":
        raise SystemExit("The synthetic browser company is required.")
    source = db.scalar(select(Source).where(Source.company_id == company.id).with_for_update())
    if source is None:
        raise SystemExit("Create the synthetic source first.")
    operation = begin_run(db, source)
    assert operation is not None
    postings = [
        Posting(
            external_id=slug,
            title=title,
            description="Synthetic job description.\nExplore the original listing.",
            url=f"https://jobs.example.com/{slug}",
            apply_url=f"https://jobs.example.com/{slug}/apply",
            locations=["London"],
        )
        for slug, title in [("strategy", "Strategy manager"), ("legal", "Legal adviser")]
    ]
    if "--matching" in sys.argv[2:]:
        sys.path.insert(0, str(root / "backend/tests"))
        from synthetic_matching import POSTINGS

        postings = POSTINGS
    apply_page(
        db,
        UUID(operation.parameters["run_id"]),
        operation.parameters["offset"],
        InventoryPage(postings=postings, complete=True),
        operation.id,
    )
    operation.state = "succeeded"
    operation.finished_at = now()
engine.dispose()
