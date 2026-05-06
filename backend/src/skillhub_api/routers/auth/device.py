"""CLI device authorization flow."""

from __future__ import annotations

import base64
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from pydantic import Field
from sqlalchemy.ext.asyncio import AsyncSession

from skillhub_api.deps import Principal, db_session, get_current_principal
from skillhub_api.errors import DomainError
from skillhub_api.schemas.base import ApiModel
from skillhub_api.services.auth.token_service import ApiTokenService

router = APIRouter(tags=["auth"])

_EXPIRES_IN_SECONDS = 900
_POLL_INTERVAL_SECONDS = 5
_USER_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_DEVICE_CODES: dict[str, "_DeviceGrant"] = {}
_USER_TO_DEVICE: dict[str, str] = {}


@dataclass
class _DeviceGrant:
    device_code: str
    user_code: str
    expires_at: datetime
    status: str = "PENDING"
    user_id: str | None = None


class DeviceCodeResponse(ApiModel):
    device_code: str
    user_code: str
    verification_uri: str
    expires_in: int
    interval: int


class DeviceTokenRequest(ApiModel):
    device_code: str = Field(min_length=1)


class DeviceTokenResponse(ApiModel):
    access_token: str | None = None
    token_type: str | None = None
    error: str | None = None


class DeviceAuthorizeRequest(ApiModel):
    user_code: str = Field(min_length=1)


class MessageResponse(ApiModel):
    message: str


def _prune_expired() -> None:
    now = datetime.now(UTC)
    expired = [code for code, grant in _DEVICE_CODES.items() if grant.expires_at <= now]
    for code in expired:
        grant = _DEVICE_CODES.pop(code, None)
        if grant is not None:
            _USER_TO_DEVICE.pop(grant.user_code, None)


def _new_device_code() -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode("ascii")


def _new_user_code() -> str:
    chars = [secrets.choice(_USER_CODE_ALPHABET) for _ in range(8)]
    return "".join(chars[:4]) + "-" + "".join(chars[4:])


@router.post("/api/v1/auth/device/code", response_model=DeviceCodeResponse)
async def request_device_code() -> DeviceCodeResponse:
    _prune_expired()
    device_code = _new_device_code()
    user_code = _new_user_code()
    while user_code in _USER_TO_DEVICE:
        user_code = _new_user_code()
    grant = _DeviceGrant(
        device_code=device_code,
        user_code=user_code,
        expires_at=datetime.now(UTC) + timedelta(seconds=_EXPIRES_IN_SECONDS),
    )
    _DEVICE_CODES[device_code] = grant
    _USER_TO_DEVICE[user_code] = device_code
    return DeviceCodeResponse(
        device_code=device_code,
        user_code=user_code,
        verification_uri="/device",
        expires_in=_EXPIRES_IN_SECONDS,
        interval=_POLL_INTERVAL_SECONDS,
    )


@router.post("/api/v1/device/authorize", response_model=MessageResponse)
async def authorize_device(
    body: DeviceAuthorizeRequest,
    principal: Principal = Depends(get_current_principal),
) -> MessageResponse:
    _prune_expired()
    user_code = body.user_code.strip().upper()
    device_code = _USER_TO_DEVICE.get(user_code)
    if device_code is None:
        raise DomainError("DEVICE_CODE_INVALID", "invalid or expired user code")
    grant = _DEVICE_CODES.get(device_code)
    if grant is None:
        raise DomainError("DEVICE_CODE_INVALID", "invalid or expired user code")
    if grant.status == "USED":
        raise DomainError("DEVICE_CODE_USED", "device code already used")
    if grant.status == "AUTHORIZED" and grant.user_id != principal.user_id:
        raise DomainError("DEVICE_CODE_ALREADY_AUTHORIZED", "device code already authorized")
    grant.status = "AUTHORIZED"
    grant.user_id = principal.user_id
    return MessageResponse(message="Device authorized successfully")


@router.post("/api/v1/auth/device/token", response_model=DeviceTokenResponse)
async def poll_device_token(
    body: DeviceTokenRequest,
    db: AsyncSession = Depends(db_session),
) -> DeviceTokenResponse:
    _prune_expired()
    grant = _DEVICE_CODES.get(body.device_code)
    if grant is None:
        raise DomainError("DEVICE_CODE_INVALID", "invalid or expired device code")
    if grant.status == "PENDING":
        return DeviceTokenResponse(error="authorization_pending")
    if grant.status == "USED":
        raise DomainError("DEVICE_CODE_USED", "device code already used")
    if not grant.user_id:
        raise DomainError("DEVICE_CODE_INVALID", "device code is not bound to a user")

    token_service = ApiTokenService(db)
    row, minted = await token_service.create(
        user_id=grant.user_id,
        name=f"CLI Device Flow {grant.device_code[:6]}",
        scope=["skill:read", "skill:publish"],
    )
    _ = row
    grant.status = "USED"
    _USER_TO_DEVICE.pop(grant.user_code, None)
    await db.commit()
    return DeviceTokenResponse(access_token=minted.plaintext, token_type="Bearer")
