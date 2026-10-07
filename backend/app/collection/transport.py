"""Worker-to-fetcher RPC. Job URLs never select the RPC host or its credentials."""

import json
from typing import Any
from urllib.parse import urlsplit

import httpx
from app.config import get_settings
from app.fetcher.contracts import FetchRequest, FetchResult
from app.services.operations import OperationError
from pydantic import ValidationError

MAX_RPC_BODY = 64 * 1024 * 1024  # Worst-case JSON escaping of the bounded 10 MiB text body.


def client() -> httpx.Client:
    settings = get_settings()
    if not settings.fetcher_url:
        raise OperationError(
            "fetcher_unavailable",
            "Job collection is not configured. Existing vacancies are preserved.",
            blocked=True,
        )
    parts = urlsplit(settings.fetcher_url)
    if (
        parts.scheme not in {"http", "https"}
        or not parts.hostname
        or parts.username
        or parts.password
        or parts.query
        or parts.fragment
    ):
        raise OperationError(
            "fetcher_configuration", "Review the internal fetcher configuration.", blocked=True
        )
    try:
        token = settings.fetcher_token_file.read_text().strip()
    except OSError:
        token = ""
    if len(token) < 32:
        raise OperationError(
            "fetcher_configuration", "The internal fetcher credential is missing.", blocked=True
        )
    return httpx.Client(
        base_url=settings.fetcher_url.rstrip("/") + "/",
        trust_env=False,
        follow_redirects=False,
        timeout=40,
        headers={"Authorization": "Bearer " + token},
    )


def fetch_document(request: FetchRequest) -> FetchResult:
    try:
        with client() as http, http.stream("POST", "fetch", json=request.model_dump()) as response:
            body = bytearray()
            for chunk in response.iter_bytes(chunk_size=65536):
                body.extend(chunk)
                if len(body) > MAX_RPC_BODY:
                    raise OperationError(
                        "fetcher_response_large", "The fetcher response exceeded its limit."
                    )
            if response.status_code != 200:
                try:
                    failure = json.loads(body)
                    code = failure.get("code", "fetcher_unavailable")
                    delay = failure.get("retry_after")
                    if (
                        not isinstance(code, str)
                        or len(code) > 80
                        or not code.replace("_", "").isalnum()
                    ):
                        raise ValueError
                    if delay is not None and (type(delay) is not int or not 0 <= delay <= 10**12):
                        raise ValueError
                except (ValueError, TypeError, AttributeError):
                    code, delay = "fetcher_unavailable", None
                raise OperationError(
                    code,
                    "The source could not be checked. Existing listings are preserved.",
                    blocked=delay is None,
                    retryable=delay is not None,
                    retry_after=min(delay, 30 * 86400) if delay is not None else None,
                )
            return FetchResult.model_validate_json(bytes(body))
    except httpx.HTTPError:
        raise OperationError(
            "fetcher_transport", "The job-page service could not be reached.", retryable=True
        ) from None
    except ValidationError:
        raise OperationError(
            "fetcher_response_invalid", "The job-page service returned an invalid response."
        ) from None


def fetch_json(url: str) -> Any:
    document = fetch_document(FetchRequest(url=url))
    if document.status == 429 or document.status >= 500:
        raise OperationError(
            "source_unavailable",
            "This job source is temporarily unavailable.",
            retryable=True,
            retry_after=min(document.retry_after or 60, 30 * 86400),
        )
    if document.status != 200:
        raise OperationError(
            "source_http_error",
            "This source did not return a usable job inventory.",
            blocked=document.status in {401, 403, 404},
        )
    media_type = document.content_type.split(";", 1)[0].strip().lower()
    if media_type != "application/json" and not media_type.endswith("+json"):
        raise OperationError("source_content_type", "This source did not return a JSON inventory.")
    try:
        return json.loads(document.body)
    except ValueError:
        raise OperationError(
            "source_invalid_json", "This source returned an unreadable job inventory."
        ) from None
