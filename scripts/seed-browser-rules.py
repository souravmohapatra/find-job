"""Populate synthetic website extraction evidence in the fixed disposable browser database only."""

import sys
from pathlib import Path
from uuid import UUID

from sqlalchemy import URL, create_engine, select
from sqlalchemy.orm import Session

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "backend"))
from app.collection.cache import key  # noqa: E402
from app.collection.models import Company, Source, SourceSnapshot  # noqa: E402
from app.fetcher.contracts import FetchResult  # noqa: E402
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
    if company is None or company.label != "Synthetic Rules":
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
    url = "https://example.com/careers"
    row = Source(
        company_id=company.id,
        identity=key(url),
        adapter="generic_http",
        url=url,
        authoritative=False,
        enabled=False,
        config={"company_name": company.label, "website": "https://example.com"},
    )
    db.add(row)
    db.flush()
    body = (
        '<article class="job"><h2>Strategy manager</h2>'
        '<a href="/jobs/strategy">Apply</a><p class="description">Plan new markets</p>'
        '<span class="employer">Synthetic Rules</span></article>'
    )
    document = FetchResult(url=url, status=200, content_type="text/html", body=body)
    db.add(
        SourceSnapshot(
            source_id=row.id,
            url_hash=key(url),
            source_revision=1,
            document=document.model_dump(mode="json"),
            body_hash=key(body),
            fetched_at=now(),
        )
    )
engine.dispose()
