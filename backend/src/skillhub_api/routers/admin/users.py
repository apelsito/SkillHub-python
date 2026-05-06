"""Admin user management — /api/v1/admin/users/*.

Ports the Java ``UserManagementController`` contract. Search + filter +
pagination on list; mutation endpoints for role / status / password reset.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from skillhub_api.deps import Principal, db_session, require_any_role
from skillhub_api.domain.auth import UserStatus
from skillhub_api.errors import ConflictError, NotFoundError
from skillhub_api.infra.db.models.auth import Role, UserRoleBinding
from skillhub_api.infra.db.models.user import LocalCredential, UserAccount
from skillhub_api.infra.repositories.role import RoleRepository
from skillhub_api.schemas.admin import (
    AdminUserListResponse,
    AdminUserMutationResponse,
    AdminUserRoleUpdate,
    AdminUserStatusUpdate,
    AdminUserSummary,
)

router = APIRouter(prefix="/api/v1/admin/users", tags=["admin"])

_USER_ADMIN_ROLES = ("SUPER_ADMIN", "USER_ADMIN")


async def _summaries(db: AsyncSession, users: list[UserAccount]) -> list[AdminUserSummary]:
    if not users:
        return []
    ids = [u.id for u in users]

    # Fetch usernames from local_credential (optional — OAuth-only users won't have one).
    username_map: dict[str, str] = {
        uid: name
        for uid, name in (
            await db.execute(
                select(LocalCredential.user_id, LocalCredential.username).where(
                    LocalCredential.user_id.in_(ids)
                )
            )
        ).all()
    }

    # Fetch roles per user in one query.
    role_rows = (
        await db.execute(
            select(UserRoleBinding.user_id, Role.code)
            .join(Role, Role.id == UserRoleBinding.role_id)
            .where(UserRoleBinding.user_id.in_(ids))
        )
    ).all()
    role_map: dict[str, list[str]] = {}
    for uid, code in role_rows:
        role_map.setdefault(uid, []).append(code)

    return [
        AdminUserSummary(
            id=u.id,
            display_name=u.display_name,
            username=username_map.get(u.id),
            email=u.email,
            status=u.status,
            platform_roles=sorted(role_map.get(u.id, [])),
            created_at=u.created_at,
        )
        for u in users
    ]


@router.get("", response_model=AdminUserListResponse)
async def list_users(
    q: str | None = Query(default=None, description="free-text search on display/email/username"),
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _principal: Principal = Depends(require_any_role(*_USER_ADMIN_ROLES)),
    db: AsyncSession = Depends(db_session),
) -> AdminUserListResponse:
    conditions: list = []
    if status_filter is not None:
        conditions.append(UserAccount.status == status_filter)
    if q:
        needle = f"%{q.lower()}%"
        # LOWER() on three fields — index coverage is best-effort.
        conditions.append(
            or_(
                func.lower(UserAccount.display_name).like(needle),
                func.lower(UserAccount.email).like(needle),
                UserAccount.id.in_(
                    select(LocalCredential.user_id).where(
                        func.lower(LocalCredential.username).like(needle)
                    )
                ),
            )
        )
    base = select(UserAccount)
    if conditions:
        base = base.where(and_(*conditions))
    total = int((await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one())
    stmt = base.order_by(UserAccount.created_at.desc()).offset(offset).limit(limit)
    users = list((await db.execute(stmt)).scalars())
    return AdminUserListResponse(
        items=await _summaries(db, users), total=total, limit=limit, offset=offset
    )


@router.put("/{userId}/role", response_model=AdminUserMutationResponse)
async def update_role(
    userId: str,
    body: AdminUserRoleUpdate,
    _principal: Principal = Depends(require_any_role(*_USER_ADMIN_ROLES)),
    db: AsyncSession = Depends(db_session),
) -> AdminUserMutationResponse:
    user = await db.get(UserAccount, userId)
    if user is None:
        raise NotFoundError("USER_NOT_FOUND", "user not found")
    roles = RoleRepository(db)
    role = await roles.find_by_code(body.role)
    if role is None:
        raise NotFoundError("ROLE_NOT_FOUND", f"role {body.role!r} not found")
    await roles.bind_user(user.id, role.id)
    await db.commit()
    return AdminUserMutationResponse(user_id=user.id, status=user.status)


@router.put("/{userId}/status", response_model=AdminUserMutationResponse)
async def update_status(
    userId: str,
    body: AdminUserStatusUpdate,
    _principal: Principal = Depends(require_any_role(*_USER_ADMIN_ROLES)),
    db: AsyncSession = Depends(db_session),
) -> AdminUserMutationResponse:
    user = await db.get(UserAccount, userId)
    if user is None:
        raise NotFoundError("USER_NOT_FOUND", "user not found")
    user.status = body.status
    user.updated_at = datetime.now(UTC)
    await db.commit()
    return AdminUserMutationResponse(user_id=user.id, status=user.status)


async def _transition_status(
    db: AsyncSession, user_id: str, *, from_status: str | None, to_status: str
) -> AdminUserMutationResponse:
    user = await db.get(UserAccount, user_id)
    if user is None:
        raise NotFoundError("USER_NOT_FOUND", "user not found")
    if from_status is not None and user.status != from_status:
        raise ConflictError("INVALID_TRANSITION", f"user must be {from_status} (is {user.status})")
    user.status = to_status
    user.updated_at = datetime.now(UTC)
    await db.commit()
    return AdminUserMutationResponse(user_id=user.id, status=user.status)


@router.post("/{userId}/approve", response_model=AdminUserMutationResponse)
async def approve_user(
    userId: str,
    _principal: Principal = Depends(require_any_role(*_USER_ADMIN_ROLES)),
    db: AsyncSession = Depends(db_session),
) -> AdminUserMutationResponse:
    return await _transition_status(
        db, userId, from_status=UserStatus.PENDING.value, to_status=UserStatus.ACTIVE.value
    )


@router.post("/{userId}/disable", response_model=AdminUserMutationResponse)
async def disable_user(
    userId: str,
    _principal: Principal = Depends(require_any_role(*_USER_ADMIN_ROLES)),
    db: AsyncSession = Depends(db_session),
) -> AdminUserMutationResponse:
    return await _transition_status(
        db, userId, from_status=None, to_status=UserStatus.DISABLED.value
    )


@router.post("/{userId}/enable", response_model=AdminUserMutationResponse)
async def enable_user(
    userId: str,
    _principal: Principal = Depends(require_any_role(*_USER_ADMIN_ROLES)),
    db: AsyncSession = Depends(db_session),
) -> AdminUserMutationResponse:
    return await _transition_status(
        db, userId, from_status=UserStatus.DISABLED.value, to_status=UserStatus.ACTIVE.value
    )


@router.post(
    "/{userId}/password-reset",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def admin_trigger_password_reset(
    userId: str,
    principal: Principal = Depends(require_any_role(*_USER_ADMIN_ROLES)),
    db: AsyncSession = Depends(db_session),
) -> None:
    """Admin-initiated password reset.

    Creates a reset-code row; in production the user receives the code by
    email. Until the mail backend lands (Phase 8), admins can fetch the
    debug code from the password-reset endpoint when direct-auth mode
    is on.
    """
    from skillhub_api.services.auth.password_reset import PasswordResetService

    user = await db.get(UserAccount, userId)
    if user is None:
        raise NotFoundError("USER_NOT_FOUND", "user not found")
    if not user.email:
        raise ConflictError("NO_EMAIL", "user has no email on file")
    svc = PasswordResetService(db)
    await svc.request_reset(email=user.email)
    await db.commit()
    _ = principal  # audit handled by the event listener
