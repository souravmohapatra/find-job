import os
from collections.abc import Generator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import text

# Tests require a deliberately named disposable PostgreSQL database.
url = os.environ.get("TEST_DATABASE_URL", "")
if not url or not url.rsplit("/", 1)[-1].startswith("jobfinder_test"):
    raise RuntimeError("Set TEST_DATABASE_URL to an isolated jobfinder_test* PostgreSQL database")
os.environ["JOBFINDER_DATABASE_URL"] = url
os.environ["JOBFINDER_ENVIRONMENT"] = "test"
os.environ["JOBFINDER_ALLOWED_ORIGINS"] = '["https://testserver"]'
os.environ["JOBFINDER_ALLOWED_HOSTS"] = '["testserver"]'

from app.cli import create_owner  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.db import get_engine  # noqa: E402
from app.main import create_app  # noqa: E402
from app.tasks.worker import bootstrap_queue  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def migrate() -> Generator[None, None, None]:
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    config.set_main_option("script_location", str(Path(__file__).parents[1] / "migrations"))
    command.upgrade(config, "head")
    bootstrap_queue()
    yield
    get_engine().dispose()


@pytest.fixture(autouse=True)
def clean_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "document_dir", tmp_path / "documents")
    monkeypatch.setattr(get_settings(), "integration_mode", "mock")
    monkeypatch.setattr(get_settings(), "search_mode", "mock")
    with get_engine().begin() as connection:
        connection.execute(
            text(
                "TRUNCATE notification_settings, notification_digests, search_state, companies, "
                "inference_calls, ai_task_revisions, "
                "ai_limits, sessions,"
                " login_buckets, users, profile_revisions, profile_drafts, "
                "profiles, documents, operation_intents, procrastinate_jobs CASCADE"
            )
        )
    create_owner("owner", "synthetic-test-password")


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    with TestClient(create_app(), base_url="https://testserver") as client:
        yield client
