"""Auth method / provider discovery — /api/v1/auth/{methods,providers}.

Ports ``AuthMethodCatalog`` from Java. The UI calls these at page load
to render the login screen dynamically (local form, OAuth buttons,
etc.), so they must exist even when only local auth is wired.
"""

from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Query
from pydantic import BaseModel

from skillhub_api.settings import get_settings

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class AuthProviderResponse(BaseModel):
    id: str
    name: str
    authorizationUrl: str


class AuthMethodResponse(BaseModel):
    id: str
    methodType: str
    provider: str
    displayName: str
    actionUrl: str


def _sanitize_return_to(return_to: str | None) -> str | None:
    if not return_to:
        return None
    # Only allow same-origin relative paths to avoid open-redirect abuse.
    if not return_to.startswith("/") or return_to.startswith("//"):
        return None
    return return_to


def _authorization_url(registration_id: str, return_to: str | None) -> str:
    base = f"/oauth2/authorization/{registration_id}"
    if return_to is None:
        return base
    return f"{base}?returnTo={quote(return_to, safe='')}"


def _oauth_registrations() -> list[tuple[str, str]]:
    """Return ``[(registration_id, display_name)]`` from settings.

    We only surface registrations whose client id looks real — placeholder
    values shouldn't appear on the login screen.
    """
    settings = get_settings().oauth
    providers: list[tuple[str, str]] = []
    if settings.github_client_id and settings.github_client_id != "placeholder":
        providers.append(("github", "GitHub"))
    if settings.gitlab_client_id and settings.gitlab_client_id != "placeholder":
        providers.append(("gitlab", settings.gitlab_display_name or "GitLab"))
    return sorted(providers, key=lambda p: p[0])


@router.get("/providers", response_model=list[AuthProviderResponse])
async def list_providers(returnTo: str | None = Query(default=None)) -> list[AuthProviderResponse]:
    sanitized = _sanitize_return_to(returnTo)
    return [
        AuthProviderResponse(
            id=pid,
            name=display,
            authorizationUrl=_authorization_url(pid, sanitized),
        )
        for pid, display in _oauth_registrations()
    ]


@router.get("/methods", response_model=list[AuthMethodResponse])
async def list_methods(returnTo: str | None = Query(default=None)) -> list[AuthMethodResponse]:
    sanitized = _sanitize_return_to(returnTo)
    settings = get_settings()
    methods: list[AuthMethodResponse] = [
        AuthMethodResponse(
            id="local-password",
            methodType="PASSWORD",
            provider="local",
            displayName="Local Account",
            actionUrl="/api/v1/auth/local/login",
        )
    ]
    for pid, display in _oauth_registrations():
        methods.append(
            AuthMethodResponse(
                id=f"oauth-{pid}",
                methodType="OAUTH_REDIRECT",
                provider=pid,
                displayName=display,
                actionUrl=_authorization_url(pid, sanitized),
            )
        )
    if settings.auth.direct_enabled:
        methods.append(
            AuthMethodResponse(
                id="direct-local",
                methodType="DIRECT_PASSWORD",
                provider="local",
                displayName="Local Account (direct)",
                actionUrl="/api/v1/auth/direct/login",
            )
        )
    return methods
