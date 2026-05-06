"""Role/permission lookups for RBAC."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from skillhub_api.infra.db.models.auth import Role, UserRoleBinding


class RoleRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_by_code(self, code: str) -> Role | None:
        stmt = select(Role).where(Role.code == code).limit(1)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def bind_user(self, user_id: str, role_id: int) -> None:
        existing = await self._session.execute(
            select(UserRoleBinding)
            .where(UserRoleBinding.user_id == user_id)
            .where(UserRoleBinding.role_id == role_id)
            .limit(1)
        )
        if existing.scalar_one_or_none():
            return
        self._session.add(UserRoleBinding(user_id=user_id, role_id=role_id))
        await self._session.flush()

    async def roles_for_user(self, user_id: str) -> list[str]:
        stmt = (
            select(Role.code)
            .join(UserRoleBinding, UserRoleBinding.role_id == Role.id)
            .where(UserRoleBinding.user_id == user_id)
        )
        return list((await self._session.execute(stmt)).scalars())
