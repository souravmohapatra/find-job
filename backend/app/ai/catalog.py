"""Bounded catalog metadata cache; no prompts or provider credentials in returned data."""

import time
from threading import Lock
from typing import Any

import httpx
from app.ai import provider
from app.config import get_settings
from app.services.operations import OperationError

_lock = Lock()
_cached: tuple[float, list[dict[str, Any]]] = (0, [])


def models() -> list[dict[str, Any]]:
    global _cached
    if get_settings().integration_mode == "mock":
        return [
            {
                "id": "example/synthetic",
                "name": "Synthetic development model",
                "context_length": 128000,
                "supported_parameters": ["response_format", "structured_outputs"],
            }
        ]
    with _lock:
        if time.monotonic() - _cached[0] < 900 and _cached[1]:
            return _cached[1]
        try:
            with provider.client() as http:
                response = http.get("models")
                if response.status_code != 200:
                    raise provider.http_failure(response)
                entries = response.json()["data"]
                result = []
                for entry in entries[:10000]:
                    if not isinstance(entry.get("id"), str) or not isinstance(
                        entry.get("name"), str
                    ):
                        continue
                    result.append(
                        {
                            "id": entry["id"][:200],
                            "name": entry["name"][:200],
                            "context_length": entry.get("context_length"),
                            "supported_parameters": entry.get("supported_parameters", []),
                        }
                    )
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as error:
            raise OperationError(
                "ai_catalog_unavailable",
                "The model catalog is unavailable. Existing settings are preserved.",
                blocked=True,
            ) from error
        _cached = (time.monotonic(), result)
        return result
