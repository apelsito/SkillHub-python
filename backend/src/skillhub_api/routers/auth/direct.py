"""Direct-auth and passive session bootstrap routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from skillhub_api.deps import SESSION_PRINCIPAL_KEY, db_session
from skillhub_api.errors import DomainError, ForbiddenError, UnauthorizedError
from skillhub_api.infra.db.models.user import UserAccount
from skillhub_api.infra.repositories.role import RoleRepository
from skillhub_api.schemas.auth import AuthMeResponse
from skillhub_api.schemas.base import ApiModel
from skillhub_api.services.auth.local import LocalAuthService
from skillhub_api.settings import get_settings

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class DirectLoginRequest(ApiModel):
    provider: str
    username: str
    password: str


class SessionBootstrapRequest(ApiModel):
    provider: str


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


@router.post("/direct/login", response_model=AuthMeResponse)
async def direct_login(
    body: DirectLoginRequest,
    request: Request,
    db: AsyncSession = Depends(db_session),
) -> AuthMeResponse:
    settings = get_settings()
    if not settings.auth.direct_enabled:
        raise ForbiddenError("DIRECT_AUTH_DISABLED", "direct authentication is disabled")
    if body.provider != "local":
        raise DomainError("DIRECT_AUTH_PROVIDER_UNSUPPORTED", "direct auth provider is unsupported")
    svc = LocalAuthService(db)
    user = await svc.login(username=body.username, password=body.password)
    await db.commit()
    _establish_session(request, user)
    return await _me_response(user, db)


@router.post("/session/bootstrap", response_model=AuthMeResponse)
async def session_bootstrap(
    body: SessionBootstrapRequest,
    request: Request,
    db: AsyncSession = Depends(db_session),
) -> AuthMeResponse:
    settings = get_settings()
    if not settings.auth.session_bootstrap_enabled:
        raise ForbiddenError("SESSION_BOOTSTRAP_DISABLED", "session bootstrap is disabled")
    if body.provider != "session":
        raise DomainError(
            "SESSION_BOOTSTRAP_PROVIDER_UNSUPPORTED",
            "session bootstrap provider is unsupported",
        )
    principal_data = request.session.get(SESSION_PRINCIPAL_KEY)
    if not principal_data:
        raise UnauthorizedError("SESSION_BOOTSTRAP_NOT_AUTHENTICATED", "no authenticated session to bootstrap")
    user = await db.get(UserAccount, principal_data["user_id"])
    if user is None:
        raise UnauthorizedError("SESSION_BOOTSTRAP_NOT_AUTHENTICATED", "no authenticated session to bootstrap")
    _establish_session(request, user)
    return await _me_response(user, db)
