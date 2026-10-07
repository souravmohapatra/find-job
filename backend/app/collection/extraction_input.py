"""Bounded public-page handoff between fetch and AI queues."""

from app.collection.cache import SnapshotUpdate
from app.collection.contracts import InventoryPage, public_link
from app.collection.generic import PageLink
from pydantic import BaseModel, Field, field_validator


class PublicPage(BaseModel):
    url: str
    text: str = Field(min_length=1, max_length=40_000)
    links: list[PageLink] = Field(default_factory=list, max_length=1000)

    @field_validator("url")
    @classmethod
    def public_url(cls, value: str) -> str:
        return public_link(value)


class PreparedPage(InventoryPage):
    snapshot: SnapshotUpdate | None = Field(default=None, exclude=True)
    extraction: PublicPage | None = None
