"""Generate project-local development secrets without touching the user's .env."""

import os
import secrets
from pathlib import Path

root = Path(__file__).resolve().parents[1]
folder = root / ".secrets"
folder.mkdir(mode=0o700, exist_ok=True)
for name in ["db_password", "test_db_password"]:
    target = folder / name
    if not target.exists():
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as stream:
            stream.write(secrets.token_urlsafe(32) + "\n")
print("Development secrets ready. Existing values and .env were preserved.")
