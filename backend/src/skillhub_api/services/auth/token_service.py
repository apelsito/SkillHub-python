"""Application-layer service for API token CRUD.

Named ``token_service`` to avoid colliding with the ``tokens`` module that
holds the hashing primitives.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from skillhub_api.errors import ConflictError, NotFoundError
from skillhub_api.infra.db.models.auth import ApiToken
from skillhub_api.infra.repositories.token import ApiTokenRepository
from skillhub_api.services.auth.tokens import GeneratedToken, generate_token


class ApiTokenService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = ApiTokenRepository(session)

    async def create(
        self,
        *,
        user_id: str,
        name: str,
        scope: list[str],
        expires_at: datetime | None = None,
    ) -> tuple[ApiToken, GeneratedToken]:
        if await self._repo.find_active_by_name(user_id, name):
            raise ConflictError("TOKEN_NAME_TAKEN", "an active token with that name already exists")
        minted = generate_token()
        row = await self._repo.create(
            user_id=user_id,
            name=name,
            token_prefix=minted.prefix,
            token_hash=minted.hash_hex,
            scope=scope,
            expires_at=expires_at,
        )
        return row, minted

    async def list_for_user(self, user_id: str) -> list[ApiToken]:
        return await self._repo.list_for_user(user_id)

    async def list_active_for_user(
        self, user_id: str, *, limit: int, offset: int
    ) -> tuple[list[ApiToken], int]:
        return await self._repo.list_active_for_user(user_id, limit=limit, offset=offset)

    async def revoke(self, *, user_id: str, token_id: int) -> None:
        token = await self._repo.get_owned(user_id, token_id)
        if token is None:
            raise NotFoundError("TOKEN_NOT_FOUND", "token does not exist or is not yours")
        if token.revoked_at is not None:
            return
        await self._repo.revoke(token, datetime.now(UTC))

    async def update_expiration(
        self, *, user_id: str, token_id: int, expires_at: datetime | None
    ) -> ApiToken:
        token = await self._repo.get_owned(user_id, token_id)
        if token is None:
            raise NotFoundError("TOKEN_NOT_FOUND", "token does not exist or is not yours")
        if token.revoked_at is not None:
            raise NotFoundError("TOKEN_NOT_FOUND", "token does not exist or is not yours")
        await self._repo.update_expiration(token, expires_at)
        return token
