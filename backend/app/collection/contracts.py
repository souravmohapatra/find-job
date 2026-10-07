"""Transport-independent inventory contracts; no candidate profile enters collection."""

import hashlib
import ipaddress
import json
from datetime import datetime
from typing import Any, Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator

Adapter = Literal["greenhouse", "lever", "ashby"]


def public_link(value: str) -> str:
    """Validate stored links; fetch-time DNS/connection isolation is a separate requirement."""
    parts = urlsplit(value)
    host = parts.hostname
    if (
        parts.scheme not in {"http", "https"}
        or not host
        or parts.username is not None
        or parts.password is not None
        or parts.port not in {None, 80, 443}
        or len(value) > 4096
        or any(ord(char) < 33 for char in value)
        or "\\" in value
    ):
        raise ValueError("Use an ordinary public HTTP or HTTPS job URL.")
    host = host.rstrip(".").lower()
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        if "." not in host or host.endswith((".localhost", ".local", ".internal", ".ts.net")):
            raise ValueError("Use a public hostname.") from None
    else:
        if not address.is_global:
            raise ValueError("Private and reserved addresses are not job sources.")
    netloc = f"[{host}]" if ":" in host else host
    if parts.port and (parts.scheme, parts.port) not in {("https", 443), ("http", 80)}:
        netloc += f":{parts.port}"
    query = urlencode(
        [
            (key, val)
            for key, val in parse_qsl(parts.query, keep_blank_values=True)
            if not key.lower().startswith("utm_") and key.lower() not in {"gclid", "fbclid"}
        ]
    )
    return urlunsplit((parts.scheme, netloc, parts.path or "/", query, ""))


class Posting(BaseModel):
    model_config = ConfigDict(extra="forbid")
    external_id: str = Field(min_length=1, max_length=4096)
    title: str = Field(min_length=1, max_length=1000)
    url: str
    apply_url: str
    description: str = Field(min_length=1, max_length=200_000)
    locations: list[str] = Field(default_factory=list, max_length=200)
    workplace: str | None = None
    employment_type: str | None = None
    department: str | None = None
    salary: dict[str, Any] | None = None
    published_at: datetime | None = None

    @field_validator("url", "apply_url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        return public_link(value)

    @field_validator("published_at")
    @classmethod
    def timezone_required(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("Published timestamps must include a timezone.")
        return value

    def content_hash(self) -> str:
        data = self.model_dump(mode="json", exclude={"external_id"})
        return hashlib.sha256(
            json.dumps(data, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()


class InventoryPage(BaseModel):
    postings: list[Posting]
    complete: bool
    next_offset: int | None = None
    issues: list[str] = Field(default_factory=list)
