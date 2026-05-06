"""Pydantic DTOs for auth endpoints.

Field names match the Java request/response shapes so the React frontend's
generated openapi-fetch types round-trip unchanged.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import EmailStr, Field, field_serializer, field_validator

from skillhub_api.schemas.base import ApiModel


def _iso_z(value: datetime) -> str:
    """Serialize datetime to ISO-8601 with a trailing Z to match Jackson."""
    if value.tzinfo is None:
        return value.isoformat() + "Z"
    return value.isoformat().replace("+00:00", "Z")


class LocalRegisterRequest(ApiModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=256)
    email: EmailStr | None = None
    display_name: str | None = Field(default=None, max_length=128)


class LocalLoginRequest(ApiModel):
    username: str
    password: str


class ChangePasswordRequest(ApiModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=256)


class PasswordResetRequestDto(ApiModel):
    email: EmailStr


class PasswordResetConfirmRequest(ApiModel):
    email: EmailStr
    code: str = Field(min_length=6, max_length=6)
    new_password: str = Field(min_length=8, max_length=256)


class PasswordResetAcceptedResponse(ApiModel):
    status: str = "ok"
    debug_code: str | None = None
    debug_expires_at: str | None = None


class AuthMeResponse(ApiModel):
    user_id: str
    display_name: str
    email: str | None
    status: str
    avatar_url: str | None = None
    oauth_provider: str | None = None
    platform_roles: list[str]


class TokenCreateRequest(ApiModel):
    name: str = Field(min_length=1, max_length=64)
    scope: list[str] = Field(default_factory=list)
    expires_at: datetime | None = None


class TokenExpirationUpdateRequest(ApiModel):
    expires_at: datetime | None = None

    @field_validator("expires_at", mode="before")
    @classmethod
    def _blank_to_none(cls, value):
        return None if value == "" else value


class TokenSummary(ApiModel):
    id: int
    name: str
    token_prefix: str
    scope: list[str]
    expires_at: datetime | None
    last_used_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime

    @field_serializer("expires_at", "last_used_at", "revoked_at", "created_at")
    def _ser_datetime(self, v: datetime | None) -> str | None:
        return _iso_z(v) if v is not None else None


class TokenListResponse(ApiModel):
    items: list[TokenSummary]
    total: int
    page: int
    size: int


class TokenCreateResponse(ApiModel):
    token: str
    id: int
    name: str
    token_prefix: str
    created_at: datetime
    expires_at: datetime | None

    @field_serializer("created_at", "expires_at")
    def _ser_datetime(self, v: datetime | None) -> str | None:
        return _iso_z(v) if v is not None else None
