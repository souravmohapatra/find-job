import uuid
from pathlib import Path
from typing import Any

from alembic.script import ScriptDirectory
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.ai import router as ai_router
from app.api.companies import router as companies_router
from app.api.jobs import router as jobs_router
from app.api.operations import router as operations_router
from app.api.profiles import router as profile_router
from app.auth import DB, Auth, authenticated
from app.auth import router as auth_router
from app.config import get_settings
from app.profile_models import Profile, ProfileRevision


def create_app() -> FastAPI:
    app = FastAPI(
        title="Job Finder", version="0.1.0", docs_url=None, redoc_url=None, openapi_url=None
    )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=get_settings().allowed_hosts)

    @app.middleware("http")
    async def request_context(request: Request, call_next: Any) -> Any:
        request.state.request_id = str(uuid.uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        details = (
            exc.detail
            if isinstance(exc.detail, dict)
            else {"code": "request_failed", "message": str(exc.detail)}
        )
        return JSONResponse(
            {**details, "field_errors": [], "request_id": request.state.request_id},
            status_code=exc.status_code,
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Never echo input values (especially credentials) from Pydantic's error payload.
        fields = [
            {"field": ".".join(str(x) for x in e["loc"][1:]), "message": e["msg"]}
            for e in exc.errors()
        ]
        return JSONResponse(
            {
                "code": "validation_error",
                "message": "Check the highlighted fields.",
                "field_errors": fields,
                "request_id": request.state.request_id,
            },
            status_code=422,
        )

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, exc: SQLAlchemyError) -> JSONResponse:
        return JSONResponse(
            {
                "code": "database_unavailable",
                "message": "Storage is temporarily unavailable. Try again shortly.",
                "field_errors": [],
                "request_id": request.state.request_id,
            },
            status_code=503,
        )

    app.include_router(companies_router, prefix="/api/v1")
    app.include_router(jobs_router, prefix="/api/v1")
    app.include_router(ai_router, prefix="/api/v1")
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(profile_router, prefix="/api/v1")
    app.include_router(operations_router, prefix="/api/v1")

    @app.get("/api/v1/health/live")
    def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/v1/health/ready", dependencies=[Depends(authenticated)])
    def ready(db: DB) -> dict[str, str]:
        version = db.scalar(text("SELECT version_num FROM alembic_version"))
        if (
            version
            != ScriptDirectory(
                str(Path(__file__).resolve().parents[1] / "migrations")
            ).get_current_head()
        ):
            raise HTTPException(
                503, detail={"code": "migration_required", "message": "Run migrations."}
            )
        return {"status": "ready", "schema": version}

    @app.get("/api/v1/status")
    def status(session: Auth, db: DB) -> dict[str, Any]:
        settings = get_settings()
        return {
            "environment": settings.environment,
            "integration_mode": settings.integration_mode,
            "profile_configured": bool(
                (profile := db.get(Profile, 1))
                and db.scalar(
                    select(ProfileRevision.id).where(
                        ProfileRevision.revision == profile.current_revision,
                        ProfileRevision.profile_id == 1,
                    )
                )
            ),
            "phase": "profile_review",
        }

    @app.get("/api/v1/openapi.json", dependencies=[Depends(authenticated)], include_in_schema=False)
    def openapi() -> dict[str, Any]:
        return app.openapi()

    return app


app = create_app()
