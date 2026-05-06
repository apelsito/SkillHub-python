"""API token repository."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from skillhub_api.infra.db.models.auth import ApiToken


class ApiTokenRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        user_id: str,
        name: str,
        token_prefix: str,
        token_hash: str,
        scope: list[str],
        expires_at: datetime | None,
    ) -> ApiToken:
        token = ApiToken(
            subject_type="USER",
            subject_id=user_id,
            user_id=user_id,
            name=name,
            token_prefix=token_prefix,
            token_hash=token_hash,
            scope_json=scope,
            expires_at=expires_at,
        )
        self._session.add(token)
        await self._session.flush()
        return token

    async def list_for_user(self, user_id: str) -> list[ApiToken]:
        stmt = (
            select(ApiToken).where(ApiToken.user_id == user_id).order_by(ApiToken.created_at.desc())
        )
        return list((await self._session.execute(stmt)).scalars())

    async def list_active_for_user(
        self, user_id: str, *, limit: int, offset: int
    ) -> tuple[list[ApiToken], int]:
        base = select(ApiToken).where(ApiToken.user_id == user_id, ApiToken.revoked_at.is_(None))
        total = int(
            (await self._session.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
        )
        rows = list(
            (
                await self._session.execute(
                    base.order_by(ApiToken.created_at.desc()).offset(offset).limit(limit)
                )
            ).scalars()
        )
        return rows, total

    async def find_active_by_name(self, user_id: str, name: str) -> ApiToken | None:
        stmt = (
            select(ApiToken)
            .where(
                and_(
                    ApiToken.user_id == user_id,
                    func.lower(ApiToken.name) == name.lower(),
                    ApiToken.revoked_at.is_(None),
                )
            )
            .limit(1)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_owned(self, user_id: str, token_id: int) -> ApiToken | None:
        stmt = (
            select(ApiToken)
            .where(and_(ApiToken.id == token_id, ApiToken.user_id == user_id))
            .limit(1)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def revoke(self, token: ApiToken, revoked_at: datetime) -> None:
        token.revoked_at = revoked_at
        await self._session.flush()

    async def update_expiration(self, token: ApiToken, expires_at: datetime | None) -> None:
        token.expires_at = expires_at
        await self._session.flush()


def serialize_token(token: ApiToken) -> dict[str, Any]:
    return {
        "id": token.id,
        "name": token.name,
        "token_prefix": token.token_prefix,
        "scope": token.scope_json,
        "expires_at": token.expires_at,
        "last_used_at": token.last_used_at,
        "revoked_at": token.revoked_at,
        "created_at": token.created_at,
    }
