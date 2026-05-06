"""Admin search maintenance — /api/v1/admin/search/rebuild.

Triggers a full rebuild of ``skill_search_document``. Writes an audit log
entry via the existing listener pipeline once rolled into an event; for
now the route handler commits its own audit entry directly since rebuild
is not a domain event.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from skillhub_api.deps import Principal, db_session, require_any_role
from skillhub_api.infra.db.models.audit import AuditLog
from skillhub_api.schemas.admin import RebuildSearchResponse
from skillhub_api.search.rebuild import rebuild_all

router = APIRouter(prefix="/api/v1/admin/search", tags=["admin"])


@router.post("/rebuild", response_model=RebuildSearchResponse)
async def rebuild(
    principal: Principal = Depends(require_any_role("SUPER_ADMIN")),
    db: AsyncSession = Depends(db_session),
) -> RebuildSearchResponse:
    count = await rebuild_all(db)
    db.add(
        AuditLog(
            actor_user_id=principal.user_id,
            action="search.index_rebuilt",
            target_type="system",
            detail_json={"rebuilt": count},
            created_at=datetime.now(UTC),
        )
    )
    await db.commit()
    return RebuildSearchResponse(rebuilt=count)
