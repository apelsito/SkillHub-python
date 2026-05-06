"""DTOs for search endpoints."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from skillhub_api.schemas.base import ApiModel


class SearchHitResponse(ApiModel):
    skill_id: int
    namespace_slug: str
    title: str | None
    summary: str | None
    visibility: str
    status: str
    updated_at: datetime
    score: float = Field(
        description="Relevance score (0.0-1.0 for relevance sort; 0.0 for others).",
    )


class SearchResponse(ApiModel):
    items: list[SearchHitResponse]
    total: int
    limit: int
    offset: int
