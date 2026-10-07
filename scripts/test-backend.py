"""Run the backend tests only against the dedicated disposable test database."""

import os
import subprocess
from pathlib import Path
from urllib.parse import quote

root = Path(__file__).resolve().parents[1]
password = (root / ".secrets/test_db_password").read_text().strip()
env = os.environ.copy()
env["TEST_DATABASE_URL"] = (
    f"postgresql+psycopg://jobfinder:{quote(password, safe='')}@127.0.0.1:55439/jobfinder_test"
)
raise SystemExit(
    subprocess.call(
        [str(root / "backend/.venv/bin/pytest"), *os.sys.argv[1:]],
        cwd=root / "backend",
        env=env,
    )
)
