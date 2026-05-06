"""Local auth routes — /api/v1/auth/local/*.

Parity with ``LocalAuthController.java``. Session cookie is populated on
successful login/register via Starlette's SessionMiddleware (wired in
``main.py``).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from skillhub_api.deps import (
    SESSION_PRINCIPAL_KEY,
    Principal,
    db_session,
    get_current_principal,
)
from skillhub_api.errors import DomainError
from skillhub_api.infra.db.models.user import UserAccount
from skillhub_api.infra.repositories.role import RoleRepository
from skillhub_api.schemas.auth import (
    AuthMeResponse,
    ChangePasswordRequest,
    LocalLoginRequest,
    LocalRegisterRequest,
    PasswordResetAcceptedResponse,
    PasswordResetConfirmRequest,
    PasswordResetRequestDto,
)
from skillhub_api.services.auth.local import LocalAuthService
from skillhub_api.services.auth.password_reset import PasswordResetService

router = APIRouter(prefix="/api/v1/auth/local", tags=["auth"])
logout_alias_router = APIRouter(tags=["auth"])


async def _me_response(user: UserAccount, db: AsyncSession) -> AuthMeResponse:
    roles = await RoleRepository(db).roles_for_user(user.id)
    return AuthMeResponse(
        user_id=user.id,
        display_name=user.display_name,
        email=user.email,
        status=user.status,
        avatar_url=user.avatar_url,
        oauth_provider=None,
        platform_roles=roles,
    )


def _establish_session(request: Request, user: UserAccount) -> None:
    request.session[SESSION_PRINCIPAL_KEY] = {
        "user_id": user.id,
        "display_name": user.display_name,
    }


@router.post("/register", response_model=AuthMeResponse)
async def register(
    body: LocalRegisterRequest,
    request: Request,
    db: AsyncSession = Depends(db_session),
) -> AuthMeResponse:
    svc = LocalAuthService(db)
    user = await svc.register(
        username=body.username,
        password=body.password,
        email=body.email,
        display_name=body.display_name,
    )
    await db.commit()
    _establish_session(request, user)
    return await _me_response(user, db)


@router.post("/login", response_model=AuthMeResponse)
async def login(
    body: LocalLoginRequest,
    request: Request,
    db: AsyncSession = Depends(db_session),
) -> AuthMeResponse:
    svc = LocalAuthService(db)
    try:
        user = await svc.login(username=body.username, password=body.password)
    except DomainError:
        await db.commit()
        raise
    await db.commit()
    _establish_session(request, user)
    return await _me_response(user, db)


@router.post("/logout", status_code=204)
async def logout(request: Request) -> None:
    request.session.clear()


@logout_alias_router.post("/api/v1/auth/logout", status_code=204)
async def logout_alias(request: Request) -> None:
    request.session.clear()


@router.post("/change-password", status_code=204)
async def change_password(
    body: ChangePasswordRequest,
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(db_session),
) -> None:
    svc = LocalAuthService(db)
    await svc.change_password(
        user_id=principal.user_id,
        current_password=body.current_password,
        new_password=body.new_password,
    )
    await db.commit()


@router.post("/password-reset/request", response_model=PasswordResetAcceptedResponse)
async def request_password_reset(
    body: PasswordResetRequestDto,
    db: AsyncSession = Depends(db_session),
) -> PasswordResetAcceptedResponse:
    svc = PasswordResetService(db)
    result = await svc.request_reset(email=body.email)
    await db.commit()
    return PasswordResetAcceptedResponse(**result)


@router.post("/password-reset/confirm", status_code=204)
async def confirm_password_reset(
    body: PasswordResetConfirmRequest,
    db: AsyncSession = Depends(db_session),
) -> None:
    svc = PasswordResetService(db)
    await svc.confirm(email=body.email, code=body.code, new_password=body.new_password)
    await db.commit()
