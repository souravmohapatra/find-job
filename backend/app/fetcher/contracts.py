"""Fetcher boundary: public URLs and bounded content only; no profile or provider secrets."""

from app.collection.contracts import public_link
from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_BODY = 10 * 1024 * 1024


class FetchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str = Field(max_length=4096)
    etag: str | None = Field(default=None, max_length=1000, pattern=r"^[^\r\n]*$")
    modified_since: str | None = Field(default=None, max_length=1000, pattern=r"^[^\r\n]*$")

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        return public_link(value)


class FetchResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str
    status: int
    body: str = Field(max_length=MAX_BODY)
    content_type: str = Field(max_length=300)
    etag: str | None = None
    modified: str | None = None
    retry_after: int | None = None


class FetchFailure(Exception):
    def __init__(self, code: str, *, retry_after: int | None = None):
        self.code = code
        self.retry_after = retry_after
        super().__init__(code)
