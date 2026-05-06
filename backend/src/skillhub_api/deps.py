"""Common FastAPI dependencies: DB session, current user, permission gates.

Mirrors the Spring Security setup where ``@AuthenticationPrincipal
PlatformPrincipal`` is available on authenticated endpoints. Here we read
principal data from the Starlette session cookie (populated on login) and
resolve the user row on each request.

API tokens are accepted via ``Authorization: Bearer sk_...`` — hashed and
looked up in ``api_token`` with the same algorithm Java uses.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from skillhub_api.domain.auth import UserStatus
from skillhub_api.errors import ForbiddenError, UnauthorizedError
from skillhub_api.infra.db.models.auth import (
    ApiToken,
    Permission,
    Role,
    RolePermission,
    UserRoleBinding,
)
from skillhub_api.infra.db.models.user import UserAccount
from skillhub_api.infra.db.session import get_session
from skillhub_api.services.auth.tokens import hash_token

SESSION_PRINCIPAL_KEY = "platformPrincipal"


@dataclass(frozen=True, slots=True)
class Principal:
    user_id: str
    display_name: str
    status: str
    auth_source: str  # "session" | "api_token"


async def _resolve_from_session(request: Request, db: AsyncSession) -> Principal | None:
    session = getattr(request, "session", None)
    if not session:
        return None
    payload = session.get(SESSION_PRINCIPAL_KEY)
    if not payload or not isinstance(payload, dict):
        return None
    user_id = payload.get("user_id")
    if not user_id:
        return None
    user = await db.get(UserAccount, user_id)
    if user is None:
        return None
    return Principal(
        user_id=user.id,
        display_name=user.display_name,
        status=user.status,
        auth_source="session",
    )


async def _resolve_from_bearer(request: Request, db: AsyncSession) -> Principal | None:
    header = request.headers.get("authorization")
    if not header or not header.lower().startswith("bearer "):
        return None
    plaintext = header.split(" ", 1)[1].strip()
    if not plaintext:
        return None

    token_hash = hash_token(plaintext)
    stmt = (
        select(ApiToken, UserAccount)
        .join(UserAccount, UserAccount.id == ApiToken.user_id)
        .where(ApiToken.token_hash == token_hash)
        .limit(1)
    )
    row = (await db.execute(stmt)).first()
    if row is None:
        return None
    token, user = row
    now = datetime.now(UTC)
    if token.revoked_at is not None:
        return None
    if token.expires_at is not None and token.expires_at <= now:
        return None
    if user.status != UserStatus.ACTIVE.value:
        return None
    return Principal(
        user_id=user.id,
        display_name=user.display_name,
        status=user.status,
        auth_source="api_token",
    )


async def get_current_principal_optional(
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> Principal | None:
    return await _resolve_from_session(request, db) or await _resolve_from_bearer(request, db)


async def get_current_principal(
    principal: Principal | None = Depends(get_current_principal_optional),
) -> Principal:
    if principal is None:
        raise UnauthorizedError("UNAUTHENTICATED", "login required")
    if principal.status != UserStatus.ACTIVE.value:
        raise ForbiddenError("ACCOUNT_NOT_ACTIVE", f"account status is {principal.status}")
    return principal


async def _user_permissions(db: AsyncSession, user_id: str) -> set[str]:
    """Return the permission codes granted to a user via their roles.

    SUPER_ADMIN is treated as wildcard — consistent with Java's
    ``RbacService.getUserPermissions`` where the SUPER_ADMIN shortcut returns
    every permission.
    """
    stmt = (
        select(Role.code, Permission.code)
        .join(UserRoleBinding, UserRoleBinding.role_id == Role.id)
        .join(RolePermission, RolePermission.role_id == Role.id, isouter=True)
        .join(Permission, Permission.id == RolePermission.permission_id, isouter=True)
        .where(UserRoleBinding.user_id == user_id)
    )
    codes: set[str] = set()
    is_super = False
    for role_code, perm_code in (await db.execute(stmt)).all():
        if role_code == "SUPER_ADMIN":
            is_super = True
        if perm_code:
            codes.add(perm_code)
    if is_super:
        all_perms = (await db.execute(select(Permission.code))).scalars().all()
        codes.update(all_perms)
    return codes


def require_permission(permission: str):
    """Dependency factory that enforces a single permission."""

    async def _dep(
        principal: Principal = Depends(get_current_principal),
        db: AsyncSession = Depends(get_session),
    ) -> Principal:
        perms = await _user_permissions(db, principal.user_id)
        if permission not in perms:
            raise ForbiddenError(
                "PERMISSION_DENIED",
                f"missing permission {permission}",
            )
        return principal

    return _dep


async def _user_role_codes(db: AsyncSession, user_id: str) -> set[str]:
    stmt = (
        select(Role.code)
        .join(UserRoleBinding, UserRoleBinding.role_id == Role.id)
        .where(UserRoleBinding.user_id == user_id)
    )
    return set((await db.execute(stmt)).scalars())


def require_any_role(*roles: str):
    """Dependency factory — user must hold any one of these role codes.

    Mirrors Spring's ``@PreAuthorize("hasAnyRole(...)")``. SUPER_ADMIN is
    treated as wildcard because it inherits every permission in the
    seeded RBAC graph.
    """

    allowed = set(roles)

    async def _dep(
        principal: Principal = Depends(get_current_principal),
        db: AsyncSession = Depends(get_session),
    ) -> Principal:
        user_roles = await _user_role_codes(db, principal.user_id)
        if "SUPER_ADMIN" in user_roles or user_roles & allowed:
            return principal
        raise ForbiddenError("ROLE_DENIED", f"requires one of roles {sorted(allowed)}")

    return _dep


async def db_session() -> AsyncIterator[AsyncSession]:
    async for session in get_session():
        yield session
