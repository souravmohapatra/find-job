import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.errors import problem
from app.models import LoginBucket, User, UserSession

router = APIRouter(prefix="/auth", tags=["authentication"])
DB = Annotated[Session, Depends(get_db)]
password_hasher = PasswordHasher()
DUMMY_HASH = password_hasher.hash(secrets.token_urlsafe(32))
COOKIE_NAME = "jobfinder_session"


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def require_origin(request: Request) -> None:
    if request.headers.get("origin") not in get_settings().allowed_origins:
        raise problem(
            403, "invalid_origin", "This request did not come from an allowed app origin."
        )


def authenticated(request: Request, db: DB) -> UserSession:
    token = request.cookies.get(COOKIE_NAME)
    session = db.get(UserSession, token_hash(token)) if token else None
    if session is None or session.expires_at <= datetime.now(UTC):
        raise problem(401, "unauthenticated", "Sign in to continue.")
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        require_origin(request)
        if not secrets.compare_digest(request.headers.get("x-csrf-token", ""), session.csrf_token):
            raise problem(403, "invalid_csrf", "Refresh the page and try again.")
    return session


Auth = Annotated[UserSession, Depends(authenticated)]


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=1024)


class SessionResponse(BaseModel):
    username: str
    csrf_token: str


@router.post("/login", response_model=SessionResponse)
def login(body: LoginRequest, request: Request, response: Response, db: DB) -> SessionResponse:
    require_origin(request)
    now = datetime.now(UTC)
    # Serialize each client's bucket across processes. Forwarded IPs are not trusted here.
    client = request.client.host if request.client else "unknown"
    key = token_hash(client)
    db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": key})
    bucket = db.get(LoginBucket, key)
    if bucket is None:
        bucket = LoginBucket(key=key, attempts=0, window_start=now)
        db.add(bucket)
    if bucket.window_start + timedelta(minutes=15) <= now:
        bucket.attempts = 0
        bucket.window_start = now
    if bucket.attempts >= 5:
        raise problem(429, "login_rate_limited", "Too many attempts. Try again in 15 minutes.")
    user = db.scalar(select(User).where(User.username == body.username))
    valid = False
    try:
        valid = password_hasher.verify(user.password_hash if user else DUMMY_HASH, body.password)
    except (VerificationError, InvalidHashError):
        pass
    if not valid or user is None:
        bucket.attempts += 1
        db.commit()
        raise problem(401, "invalid_credentials", "Username or password is incorrect.")
    bucket.attempts = 0
    previous = request.cookies.get(COOKIE_NAME)
    if previous:
        db.execute(delete(UserSession).where(UserSession.token_hash == token_hash(previous)))
    token = secrets.token_urlsafe(48)
    session = UserSession(
        token_hash=token_hash(token),
        user_id=user.id,
        csrf_token=secrets.token_urlsafe(32),
        created_at=now,
        expires_at=now + timedelta(days=get_settings().session_days),
    )
    db.add(session)
    db.commit()
    response.set_cookie(
        COOKIE_NAME,
        token,
        httponly=True,
        secure=get_settings().secure_cookies,
        samesite="lax",
        max_age=get_settings().session_days * 86400,
        path="/api",
    )
    return SessionResponse(username=user.username, csrf_token=session.csrf_token)


@router.get("/me", response_model=SessionResponse)
def me(session: Auth, db: DB) -> SessionResponse:
    user = db.get(User, session.user_id)
    if user is None:
        raise problem(401, "unauthenticated", "Sign in to continue.")
    return SessionResponse(username=user.username, csrf_token=session.csrf_token)


@router.post("/logout", status_code=204)
def logout(session: Auth, response: Response, db: DB) -> None:
    db.delete(session)
    db.commit()
    response.delete_cookie(
        COOKIE_NAME,
        path="/api",
        secure=get_settings().secure_cookies,
        httponly=True,
        samesite="lax",
    )
