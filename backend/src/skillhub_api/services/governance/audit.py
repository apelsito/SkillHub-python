"""Audit log read API.

Read-only filters; writes go through ``events/listeners/audit.py`` or
service-layer hooks (not this module). Admin endpoints require the
``audit:read`` permission.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from skillhub_api.infra.db.models.audit import AuditLog


class AuditLogQueryService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list(
        self,
        *,
        actor_user_id: str | None,
        action: str | None,
        target_type: str | None,
        since: datetime | None,
        until: datetime | None,
        limit: int,
        offset: int,
    ) -> tuple[list[AuditLog], int]:
        base = select(AuditLog)
        if actor_user_id:
            base = base.where(AuditLog.actor_user_id == actor_user_id)
        if action:
            base = base.where(AuditLog.action == action)
        if target_type:
            base = base.where(AuditLog.target_type == target_type)
        if since:
            base = base.where(AuditLog.created_at >= since)
        if until:
            base = base.where(AuditLog.created_at < until)

        total = (
            await self._session.execute(select(func.count()).select_from(base.subquery()))
        ).scalar_one()
        stmt = base.order_by(AuditLog.created_at.desc()).offset(offset).limit(limit)
        rows = list((await self._session.execute(stmt)).scalars())
        return rows, total
