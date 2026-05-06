"""Search endpoint — /api/v1/skills/search.

Exposes the contract equivalent of the Java ``SkillSearchController``.
Unauthenticated and cache-friendly by design; RBAC is enforced implicitly
because only PUBLIC + ACTIVE + un-hidden skills are returned.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from skillhub_api.deps import db_session
from skillhub_api.schemas.search import SearchHitResponse, SearchResponse
from skillhub_api.search.query import SearchQueryService

router = APIRouter(prefix="/api/v1/skills", tags=["search"])


@router.get("/search", response_model=SearchResponse)
async def search(
    q: str | None = Query(default=None, description="Free-text search query."),
    namespace: str | None = Query(default=None),
    sort: str = Query(default="newest", pattern=r"^(newest|downloads|rating|relevance)$"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(db_session),
) -> SearchResponse:
    svc = SearchQueryService(db)
    page = await svc.search(keyword=q, namespace=namespace, sort=sort, limit=limit, offset=offset)
    return SearchResponse(
        items=[
            SearchHitResponse(
                skill_id=h.skill_id,
                namespace_slug=h.namespace_slug,
                title=h.title,
                summary=h.summary,
                visibility=h.visibility,
                status=h.status,
                updated_at=h.updated_at,
                score=h.score,
            )
            for h in page.items
        ],
        total=page.total,
        limit=page.limit,
        offset=page.offset,
    )
