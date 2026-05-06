"""Password reset request repository."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from skillhub_api.infra.db.models.auth import PasswordResetRequest


class PasswordResetRequestRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        user_id: str,
        email: str,
        code_hash: str,
        expires_at: datetime,
        requested_by_admin: bool = False,
        requested_by_user_id: str | None = None,
    ) -> PasswordResetRequest:
        row = PasswordResetRequest(
            user_id=user_id,
            email=email,
            code_hash=code_hash,
            expires_at=expires_at,
            requested_by_admin=requested_by_admin,
            requested_by_user_id=requested_by_user_id,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def latest_pending(self, user_id: str) -> PasswordResetRequest | None:
        now = datetime.now(UTC)
        stmt = (
            select(PasswordResetRequest)
            .where(PasswordResetRequest.user_id == user_id)
            .where(PasswordResetRequest.consumed_at.is_(None))
            .where(PasswordResetRequest.expires_at > now)
            .order_by(PasswordResetRequest.created_at.desc())
            .limit(1)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def consume(self, row: PasswordResetRequest) -> None:
        row.consumed_at = datetime.now(UTC)
        await self._session.flush()
