"""Current user introspection — /api/v1/auth/me."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from skillhub_api.deps import Principal, db_session, get_current_principal
from skillhub_api.infra.db.models.user import UserAccount
from skillhub_api.infra.repositories.role import RoleRepository
from skillhub_api.schemas.auth import AuthMeResponse

router = APIRouter(tags=["auth"])


@router.get("/api/v1/auth/me", response_model=AuthMeResponse)
async def me(
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(db_session),
) -> AuthMeResponse:
    roles = await RoleRepository(db).roles_for_user(principal.user_id)
    user = await db.get(UserAccount, principal.user_id)
    return AuthMeResponse(
        user_id=principal.user_id,
        display_name=user.display_name if user is not None else principal.display_name,
        email=user.email if user is not None else None,
        status=user.status if user is not None else principal.status,
        avatar_url=user.avatar_url if user is not None else None,
        oauth_provider=None,
        platform_roles=roles,
    )
