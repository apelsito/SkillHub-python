"""Current-user profile endpoints expected by the React settings page."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, Depends
from pydantic import Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from skillhub_api.deps import Principal, db_session, get_current_principal
from skillhub_api.errors import ConflictError, NotFoundError
from skillhub_api.events.bus import EventBus, get_event_bus
from skillhub_api.infra.db.models.auth import ProfileChangeRequest
from skillhub_api.infra.db.models.user import UserAccount
from skillhub_api.schemas.base import ApiModel
from skillhub_api.services.governance.profile_change import ProfileChangeService
from skillhub_api.settings import get_settings

router = APIRouter(prefix="/api/v1/user", tags=["user"])


class FieldPolicy(ApiModel):
    editable: bool
    requires_review: bool


class PendingProfileChange(ApiModel):
    status: str
    changes: dict[str, Any]
    review_comment: str | None = None
    created_at: datetime


class UserProfileResponse(ApiModel):
    display_name: str
    avatar_url: str | None
    email: str | None
    pending_changes: PendingProfileChange | None
    field_policies: dict[str, FieldPolicy]


class UpdateProfileRequest(ApiModel):
    display_name: str | None = Field(default=None, min_length=2, max_length=32)
    avatar_url: str | None = Field(default=None, max_length=512)


class UpdateProfileResponse(ApiModel):
    status: str
    applied_fields: dict[str, str | None] | None = None
    pending_fields: dict[str, str | None] | None = None


FIELD_TO_DB = {"displayName": "display_name", "avatarUrl": "avatar_url"}
DB_TO_FIELD = {value: key for key, value in FIELD_TO_DB.items()}
DISPLAY_NAME_PATTERN = re.compile(r"^[\w\s-]+$", re.UNICODE)


def _bus_dep() -> EventBus:
    return get_event_bus()


def _to_frontend_fields(values: dict[str, Any] | None) -> dict[str, Any]:
    if not values:
        return {}
    return {DB_TO_FIELD.get(key, key): value for key, value in values.items()}


async def _latest_pending_change(db: AsyncSession, user_id: str) -> ProfileChangeRequest | None:
    return (
        await db.execute(
            select(ProfileChangeRequest)
            .where(ProfileChangeRequest.user_id == user_id)
            .where(ProfileChangeRequest.status.in_(["PENDING", "REJECTED"]))
            .order_by(desc(ProfileChangeRequest.created_at), desc(ProfileChangeRequest.id))
            .limit(1)
        )
    ).scalar_one_or_none()


def _field_policies() -> dict[str, FieldPolicy]:
    settings = get_settings()
    requires_review = settings.profile_human_review_enabled
    return {
        "displayName": FieldPolicy(editable=True, requires_review=requires_review),
        "avatarUrl": FieldPolicy(editable=True, requires_review=requires_review),
        "email": FieldPolicy(editable=False, requires_review=False),
    }


@router.get("/profile", response_model=UserProfileResponse)
async def get_profile(
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(db_session),
) -> UserProfileResponse:
    user = await db.get(UserAccount, principal.user_id)
    if user is None:
        raise NotFoundError("USER_NOT_FOUND", "user not found")
    pending = await _latest_pending_change(db, principal.user_id)
    pending_changes = None
    display_name = user.display_name
    avatar_url = user.avatar_url
    if pending is not None:
        frontend_changes = _to_frontend_fields(pending.changes)
        pending_changes = PendingProfileChange(
            status=pending.status,
            changes=frontend_changes,
            review_comment=pending.review_comment,
            created_at=pending.created_at,
        )
        if pending.status == "PENDING":
            display_name = frontend_changes.get("displayName", display_name)
            avatar_url = frontend_changes.get("avatarUrl", avatar_url)
    return UserProfileResponse(
        display_name=display_name,
        avatar_url=avatar_url,
        email=user.email,
        pending_changes=pending_changes,
        field_policies=_field_policies(),
    )


@router.patch("/profile", response_model=UpdateProfileResponse)
async def update_profile(
    body: UpdateProfileRequest,
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(db_session),
    bus: EventBus = Depends(_bus_dep),
) -> UpdateProfileResponse:
    raw = body.model_dump(exclude_unset=True, by_alias=True)
    if "displayName" in raw and raw["displayName"] is not None:
        raw["displayName"] = raw["displayName"].strip()
        if not DISPLAY_NAME_PATTERN.fullmatch(raw["displayName"]):
            raise ConflictError(
                "INVALID_DISPLAY_NAME",
                "display name can only contain letters, numbers, spaces, underscores, and hyphens",
            )
    if "avatarUrl" in raw and raw["avatarUrl"] is not None:
        raw["avatarUrl"] = raw["avatarUrl"].strip() or None
        if raw["avatarUrl"] is not None:
            parsed = urlparse(raw["avatarUrl"])
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ConflictError("INVALID_AVATAR_URL", "avatar URL must be a valid http or https URL")
    changes = {FIELD_TO_DB[key]: value for key, value in raw.items() if key in FIELD_TO_DB}
    if not changes:
        raise ConflictError("EMPTY_CHANGES", "at least one editable profile field is required")
    user = await db.get(UserAccount, principal.user_id)
    if user is None:
        raise NotFoundError("USER_NOT_FOUND", "user not found")
    changes = {key: value for key, value in changes.items() if getattr(user, key) != value}
    if not changes:
        return UpdateProfileResponse(status="NO_CHANGES", applied_fields={}, pending_fields={})

    svc = ProfileChangeService(db, bus)
    row = await svc.submit(user_id=principal.user_id, changes=changes)
    await db.commit()
    frontend_changes = _to_frontend_fields(changes)
    if row.status == "PENDING":
        return UpdateProfileResponse(status="PENDING_REVIEW", pending_fields=frontend_changes)
    return UpdateProfileResponse(status="APPLIED", applied_fields=frontend_changes)
