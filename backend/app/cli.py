import argparse
import getpass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import password_hasher
from app.db import get_engine
from app.models import User


def create_owner(username: str, password: str) -> None:
    if not 1 <= len(username) <= 100 or len(password) < 12:
        raise ValueError("Use a username and a password of at least 12 characters.")
    with Session(get_engine()) as db:
        if db.scalar(select(User.id)) is not None:
            raise ValueError("An owner already exists; initial setup cannot overwrite it.")
        db.add(
            User(
                id=1,
                username=username,
                password_hash=password_hasher.hash(password),
                created_at=datetime.now(UTC),
            )
        )
        db.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description="Local Job Finder administration")
    parser.add_argument("command", choices=["create-owner"])
    parser.add_argument("--username", default="owner")
    args = parser.parse_args()
    password = getpass.getpass("Owner password (12+ characters): ")
    if password != getpass.getpass("Repeat password: "):
        parser.error("Passwords do not match")
    try:
        create_owner(args.username, password)
    except ValueError as error:
        parser.error(str(error))
    print("Owner created. Sign in through the web portal.")


if __name__ == "__main__":
    main()
