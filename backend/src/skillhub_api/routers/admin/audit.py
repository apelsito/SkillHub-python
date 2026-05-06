"""Audit log read API — /api/v1/admin/audit-logs."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from skillhub_api.deps import Principal, db_session, require_permission
from skillhub_api.infra.db.models.audit import AuditLog
from skillhub_api.schemas.governance import AuditEntry, AuditListResponse
from skillhub_api.services.governance.audit import AuditLogQueryService

router = APIRouter(prefix="/api/v1/admin/audit-logs", tags=["admin"])


def _entry(row: AuditLog) -> AuditEntry:
    return AuditEntry(
        id=row.id,
        actor_user_id=row.actor_user_id,
        action=row.action,
        target_type=row.target_type,
        target_id=row.target_id,
        detail_json=row.detail_json,
        created_at=row.created_at,
    )


@router.get("", response_model=AuditListResponse)
async def list_audit(
    actor_user_id: str | None = Query(default=None),
    action: str | None = Query(default=None),
    target_type: str | None = Query(default=None),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _principal: Principal = Depends(require_permission("audit:read")),
    db: AsyncSession = Depends(db_session),
) -> AuditListResponse:
    svc = AuditLogQueryService(db)
    rows, total = await svc.list(
        actor_user_id=actor_user_id,
        action=action,
        target_type=target_type,
        since=since,
        until=until,
        limit=limit,
        offset=offset,
    )
    return AuditListResponse(
        items=[_entry(r) for r in rows], total=total, limit=limit, offset=offset
    )
