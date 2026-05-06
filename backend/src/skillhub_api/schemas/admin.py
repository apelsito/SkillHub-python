"""DTOs for admin endpoints."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from skillhub_api.schemas.base import ApiModel


class AdminSkillActionRequest(ApiModel):
    reason: str | None = Field(default=None, max_length=2000)


class AdminSkillMutationResponse(ApiModel):
    skill_id: int | None
    version_id: int | None
    action: str
    status: str


# --- user management ---


class AdminUserSummary(ApiModel):
    id: str
    display_name: str
    username: str | None
    email: str | None
    status: str
    platform_roles: list[str]
    created_at: datetime


class AdminUserListResponse(ApiModel):
    items: list[AdminUserSummary]
    total: int
    limit: int
    offset: int


class AdminUserRoleUpdate(ApiModel):
    role: str = Field(min_length=1, max_length=64)


class AdminUserStatusUpdate(ApiModel):
    status: str = Field(pattern=r"^(ACTIVE|PENDING|DISABLED|MERGED)$")


class AdminUserMutationResponse(ApiModel):
    user_id: str
    status: str


# --- profile reviews ---


class ProfileReviewSummary(ApiModel):
    id: int
    user_id: str
    display_name: str
    changes: dict
    old_values: dict | None
    status: str
    machine_result: str | None
    reviewer_id: str | None
    review_comment: str | None
    created_at: datetime
    reviewed_at: datetime | None


class ProfileReviewListResponse(ApiModel):
    items: list[ProfileReviewSummary]
    total: int
    limit: int
    offset: int


# --- labels ---


class LabelTranslationItem(ApiModel):
    locale: str = Field(min_length=1, max_length=16)
    display_name: str = Field(min_length=1, max_length=128)


class LabelDefinitionResponse(ApiModel):
    id: int
    slug: str
    type: str
    visible_in_filter: bool
    sort_order: int
    translations: list[LabelTranslationItem]


class LabelDefinitionListResponse(ApiModel):
    items: list[LabelDefinitionResponse]


class AdminLabelCreateRequest(ApiModel):
    slug: str = Field(min_length=1, max_length=64)
    type: str = Field(pattern=r"^(RECOMMENDED|PRIVILEGED)$")
    visible_in_filter: bool = True
    sort_order: int = 0
    translations: list[LabelTranslationItem] = Field(default_factory=list)


class AdminLabelUpdateRequest(ApiModel):
    type: str | None = Field(default=None, pattern=r"^(RECOMMENDED|PRIVILEGED)$")
    visible_in_filter: bool | None = None
    sort_order: int | None = None
    translations: list[LabelTranslationItem] | None = None


class LabelSortOrderEntry(ApiModel):
    slug: str
    sort_order: int


class LabelSortOrderUpdate(ApiModel):
    entries: list[LabelSortOrderEntry] = Field(min_length=1)


# --- skill label + tags ---


class SkillLabelDto(ApiModel):
    slug: str
    type: str
    display_name: str


class TagDto(ApiModel):
    id: int
    tag_name: str
    version_id: int
    created_at: datetime


class TagRequest(ApiModel):
    target_version: str = Field(min_length=1, max_length=64)


# --- admin search ---


class RebuildSearchResponse(ApiModel):
    rebuilt: int
