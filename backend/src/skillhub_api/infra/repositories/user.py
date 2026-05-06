"""Repository adapter for user-account reads/writes."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from skillhub_api.infra.db.models.user import IdentityBinding, LocalCredential, UserAccount


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, user_id: str) -> UserAccount | None:
        return await self._session.get(UserAccount, user_id)

    async def find_by_email(self, email: str) -> UserAccount | None:
        stmt = select(UserAccount).where(UserAccount.email == email).limit(1)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def create(
        self,
        *,
        user_id: str,
        display_name: str,
        email: str | None,
        status: str = "ACTIVE",
    ) -> UserAccount:
        now = datetime.now(UTC)
        user = UserAccount(
            id=user_id,
            display_name=display_name,
            email=email,
            status=status,
            created_at=now,
            updated_at=now,
        )
        self._session.add(user)
        await self._session.flush()
        return user


class LocalCredentialRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_by_username(self, username: str) -> LocalCredential | None:
        stmt = select(LocalCredential).where(LocalCredential.username == username).limit(1)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def find_by_user_id(self, user_id: str) -> LocalCredential | None:
        stmt = select(LocalCredential).where(LocalCredential.user_id == user_id).limit(1)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def create(
        self,
        *,
        user_id: str,
        username: str,
        password_hash: str,
    ) -> LocalCredential:
        now = datetime.now(UTC)
        cred = LocalCredential(
            user_id=user_id,
            username=username,
            password_hash=password_hash,
            failed_attempts=0,
            locked_until=None,
            created_at=now,
            updated_at=now,
        )
        self._session.add(cred)
        await self._session.flush()
        return cred


class IdentityBindingRepository:
    """Wrapper for OAuth identity bindings and account merge flows."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find(self, provider_code: str, subject: str) -> IdentityBinding | None:
        stmt = (
            select(IdentityBinding)
            .where(IdentityBinding.provider_code == provider_code)
            .where(IdentityBinding.subject == subject)
            .limit(1)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()
