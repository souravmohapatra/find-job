"""Seed synthetic accounting in the fixed disposable browser database only."""

import sys
from pathlib import Path

from sqlalchemy import URL, create_engine
from sqlalchemy.orm import Session

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "backend"))
from app.ai.configuration import latest  # noqa: E402
from app.ai.contracts import TaskConfig  # noqa: E402
from app.ai.models import InferenceCall, TaskRevision  # noqa: E402
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
    config = latest(db, "profile_analysis")
    if config is None:
        config = TaskRevision(
            task="profile_analysis",
            revision=1,
            config=TaskConfig(model="example/synthetic").model_dump(mode="json"),
        )
        db.add(config)
        db.flush()
    call = InferenceCall(
        config_id=config.id,
        task="profile_analysis",
        requested_model="example/synthetic",
        prompt_version="fixture-v1",
        schema_version="fixture-v1",
        state="unknown",
        reserved_usd="0.56",
        finished_at=now(),
    )
    db.add(call)
    db.flush()
    print(call.id)
engine.dispose()
