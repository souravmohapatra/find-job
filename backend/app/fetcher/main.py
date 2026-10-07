"""Separate fetcher ASGI entry point; imports no database or candidate services."""

import secrets

from app.fetcher.contracts import FetchFailure, FetchRequest, FetchResult
from app.fetcher.http import Fetcher
from app.fetcher.settings import FetchSettings, settings
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError


def create_app(config: FetchSettings | None = None, fetcher: Fetcher | None = None) -> FastAPI:
    config = config or settings()
    engine = fetcher or Fetcher(config)
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/health/live")
    async def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/fetch", response_model=FetchResult)
    async def fetch(request: Request) -> FetchResult | JSONResponse:
        try:
            token = config.token_file.read_text().strip()
        except OSError:
            token = ""
        if len(token) < 32:
            return JSONResponse({"code": "fetcher_not_configured"}, status_code=503)
        if not secrets.compare_digest(
            request.headers.get("authorization", "").encode(), ("Bearer " + token).encode()
        ):
            return JSONResponse({"code": "fetcher_auth"}, status_code=401)
        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > 8192:
                return JSONResponse({"code": "fetch_request_too_large"}, status_code=413)
        try:
            body = FetchRequest.model_validate_json(bytes(raw))
        except ValidationError:
            return JSONResponse({"code": "invalid_fetch_request"}, status_code=422)
        try:
            return await engine.fetch(body)
        except FetchFailure as error:
            return JSONResponse(
                {"code": error.code, "retry_after": error.retry_after}, status_code=502
            )
        except Exception:
            # Never echo untrusted page content, URLs, headers or secret/config errors.
            return JSONResponse({"code": "fetcher_failed"}, status_code=502)

    return app


app = create_app()
