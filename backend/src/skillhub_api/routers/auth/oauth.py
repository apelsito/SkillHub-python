"""OAuth2 redirect endpoints."""

from __future__ import annotations

import secrets
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse

from skillhub_api.settings import get_settings

router = APIRouter(tags=["auth"])

SUPPORTED_PROVIDERS = ("github", "gitlab")


@router.get("/login/oauth2/authorization/{provider}")
async def oauth_authorize(provider: str, request: Request) -> RedirectResponse:
    if provider not in SUPPORTED_PROVIDERS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown provider")
    settings = get_settings().oauth
    if provider == "github":
        client_id = settings.github_client_id
        authorize_url = "https://github.com/login/oauth/authorize"
        scope = "read:user user:email"
    else:
        client_id = settings.gitlab_client_id
        authorize_url = f"{settings.gitlab_base_uri.rstrip('/')}/oauth/authorize"
        scope = "read_user"
    if not client_id or client_id == "placeholder":
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"oauth {provider} is not configured")
    state = secrets.token_urlsafe(24)
    request.session[f"oauth:{provider}:state"] = state
    redirect_uri = str(request.url_for("oauth_callback", provider=provider))
    params = urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": scope,
            "state": state,
        }
    )
    return RedirectResponse(f"{authorize_url}?{params}", status_code=status.HTTP_302_FOUND)


@router.get("/login/oauth2/code/{provider}")
async def oauth_callback(
    provider: str,
    request: Request,
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
) -> RedirectResponse:
    if provider not in SUPPORTED_PROVIDERS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown provider")
    expected = request.session.pop(f"oauth:{provider}:state", None)
    if not code or not state or expected != state:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid oauth callback state")
    raise HTTPException(
        status.HTTP_400_BAD_REQUEST,
        "oauth callback token exchange is not configured for this local Python environment",
    )
