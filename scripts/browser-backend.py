"""Disposable real-backend browser fixture; binds only to loopback and never uses real CVs."""

import os
import signal
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from urllib.parse import quote

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "backend"))
import psycopg  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import text  # noqa: E402

password = (root / ".secrets/test_db_password").read_text().strip()
# A fixed, explicitly disposable database; no user-supplied target URL is accepted.
with psycopg.connect(
    host="127.0.0.1",
    port=55439,
    user="jobfinder",
    password=password,
    dbname="jobfinder_test",
    autocommit=True,
    connect_timeout=5,
) as connection:
    if not connection.execute(
        "SELECT 1 FROM pg_database WHERE datname = 'jobfinder_test_browser'"
    ).fetchone():
        connection.execute("CREATE DATABASE jobfinder_test_browser")
stop = threading.Event()
signal.signal(signal.SIGTERM, lambda *_: stop.set())
signal.signal(signal.SIGINT, lambda *_: stop.set())
with tempfile.TemporaryDirectory(prefix="jobfinder-browser-") as directory:
    os.environ.update(
        {
            "JOBFINDER_DATABASE_URL": (
                f"postgresql+psycopg://jobfinder:{quote(password, safe='')}"
                "@127.0.0.1:55439/jobfinder_test_browser"
            ),
            "JOBFINDER_ENVIRONMENT": "development",
            "JOBFINDER_INTEGRATION_MODE": "mock",
            "JOBFINDER_ALLOWED_ORIGINS": '["http://127.0.0.1:5173"]',
            "JOBFINDER_ALLOWED_HOSTS": '["127.0.0.1","localhost"]',
            "JOBFINDER_SECURE_COOKIES": "false",
            "JOBFINDER_DOCUMENT_DIR": directory,
        }
    )
    os.chdir(root / "backend")
    command.upgrade(Config("alembic.ini"), "head")
    from app.cli import create_owner
    from app.db import get_engine
    from app.tasks.worker import bootstrap_queue

    bootstrap_queue()
    with get_engine().begin() as connection:
        connection.execute(
            text(
                "TRUNCATE sessions, login_buckets, users, profile_revisions, "
                "profile_drafts, profiles, documents, operation_intents, procrastinate_jobs CASCADE"
            )
        )
    create_owner("owner", "synthetic-browser-password")
    get_engine().dispose()
    children: list[subprocess.Popen[bytes]] = []
    try:
        children.append(
            subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "app.tasks",
                    "--queues",
                    "control,ai,fetch,notify",
                    "--concurrency",
                    "2",
                ]
            )
        )
        children.append(
            subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "app.main:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "8000",
                    "--no-access-log",
                    "--no-proxy-headers",
                ]
            )
        )
        while not stop.wait(0.2):
            if any(child.poll() is not None for child in children):
                raise SystemExit("A browser fixture process stopped unexpectedly.")
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
        for child in children:
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
