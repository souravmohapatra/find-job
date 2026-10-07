from datetime import UTC, datetime, timedelta

import pytest
from app.auth import COOKIE_NAME
from app.cli import create_owner
from app.config import Settings
from app.db import get_engine
from app.models import User, UserSession
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session


def sign_in(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        headers={"Origin": "https://testserver"},
        json={"username": "owner", "password": "synthetic-test-password"},
    )
    assert response.status_code == 200
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie and "Secure" in cookie and "SameSite=lax" in cookie
    return response.json()  # type: ignore[no-any-return]


def test_private_routes_and_no_public_signup(client: TestClient) -> None:
    assert client.get("/api/v1/health/live").status_code == 200
    for path in ["/auth/me", "/status", "/health/ready", "/openapi.json"]:
        assert client.get("/api/v1" + path).status_code == 401
    assert client.post("/api/v1/auth/register", json={}).status_code == 404


def test_login_me_logout_and_token_hash(client: TestClient) -> None:
    data = sign_in(client)
    assert client.get("/api/v1/auth/me").json() == data
    assert client.get("/api/v1/health/ready").json()["status"] == "ready"
    raw = client.cookies.get(COOKIE_NAME)
    with Session(get_engine()) as db:
        stored = db.scalar(select(UserSession))
        assert stored is not None and stored.token_hash != raw
        owner = db.get(User, 1)
        assert owner is not None and owner.password_hash.startswith("$argon2id$")
    response = client.post(
        "/api/v1/auth/logout",
        headers={"Origin": "https://testserver", "X-CSRF-Token": data["csrf_token"]},
    )
    assert response.status_code == 204
    assert client.get("/api/v1/auth/me").status_code == 401


def test_origin_csrf_and_session_rotation(client: TestClient) -> None:
    assert (
        client.post("/api/v1/auth/login", json={"username": "owner", "password": "x"}).status_code
        == 403
    )
    sign_in(client)
    previous = client.cookies.get(COOKIE_NAME)
    assert (
        client.post("/api/v1/auth/logout", headers={"Origin": "https://testserver"}).status_code
        == 403
    )
    assert (
        client.post("/api/v1/auth/logout", headers={"Origin": "https://evil.example"}).status_code
        == 403
    )
    sign_in(client)
    assert client.cookies.get(COOKIE_NAME) != previous
    with Session(get_engine()) as db:
        assert len(list(db.scalars(select(UserSession)))) == 1


def test_rate_limit_persists_and_no_password_in_errors(client: TestClient) -> None:
    for _ in range(5):
        response = client.post(
            "/api/v1/auth/login",
            headers={"Origin": "https://testserver"},
            json={"username": "owner", "password": "wrong-secret"},
        )
        assert response.status_code == 401
        assert "wrong-secret" not in response.text
    assert (
        client.post(
            "/api/v1/auth/login",
            headers={"Origin": "https://testserver"},
            json={"username": "owner", "password": "synthetic-test-password"},
        ).status_code
        == 429
    )


def test_expiry(client: TestClient) -> None:
    sign_in(client)
    with get_engine().begin() as connection:
        connection.execute(
            update(UserSession).values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )
    assert client.get("/api/v1/auth/me").status_code == 401


def test_owner_cannot_be_overwritten() -> None:
    with pytest.raises(ValueError, match="already exists"):
        create_owner("intruder", "another-long-password")


def test_production_rejects_insecure_settings() -> None:
    with pytest.raises(ValueError, match="secure"):
        Settings(environment="production", secure_cookies=False)
    with pytest.raises(ValueError, match="Explicit"):
        Settings(allowed_hosts=["*"])
