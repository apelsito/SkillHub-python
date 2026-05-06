"""Pydantic DTOs for skill endpoints.

Field shapes mirror ``SkillDetailResponse.java`` /
``SkillVersionResponse.java`` so the frontend's generated types round-trip
unchanged.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import Field

from skillhub_api.domain.skill import Visibility
from skillhub_api.schemas.admin import SkillLabelDto
from skillhub_api.schemas.base import ApiModel


class SkillLifecycleVersion(ApiModel):
    id: int
    version: str
    status: str
    published_at: datetime | None = None


class SkillSummary(ApiModel):
    id: int
    namespace_id: int
    namespace: str | None = None
    slug: str
    display_name: str | None
    summary: str | None
    owner_id: str
    visibility: str
    status: str
    latest_version_id: int | None
    download_count: int
    star_count: int
    rating_avg: Decimal
    rating_count: int
    hidden: bool
    created_at: datetime
    updated_at: datetime
    can_submit_promotion: bool = False
    can_manage_lifecycle: bool = False
    can_interact: bool = True
    can_report: bool = True
    headline_version: SkillLifecycleVersion | None = None
    published_version: SkillLifecycleVersion | None = None
    owner_preview_version: SkillLifecycleVersion | None = None
    resolution_mode: str | None = None


class SkillListResponse(ApiModel):
    items: list[SkillSummary]
    total: int
    limit: int
    offset: int
    page: int | None = None
    size: int | None = None


class SkillDetailResponse(SkillSummary):
    labels: list[SkillLabelDto] = []


class SkillVersionSummary(ApiModel):
    id: int
    skill_id: int
    version: str
    status: str
    file_count: int
    total_size: int
    bundle_ready: bool
    download_ready: bool
    requested_visibility: str | None
    published_at: datetime | None
    created_at: datetime


class SkillVersionListResponse(ApiModel):
    items: list[SkillVersionSummary]
    total: int
    limit: int
    offset: int
    page: int | None = None
    size: int | None = None


class SkillVersionDetailResponse(SkillVersionSummary):
    parsed_metadata_json: dict | None
    manifest_json: dict | None
    changelog: str | None
    yanked_at: datetime | None
    yank_reason: str | None


class SkillFileResponse(ApiModel):
    file_path: str
    file_size: int
    content_type: str | None
    sha256: str


class PublishResponse(ApiModel):
    skill_id: int
    namespace_id: int
    slug: str
    version: str
    status: str
    visibility: str
    file_count: int
    total_size: int


class DownloadResponse(ApiModel):
    filename: str
    content_length: int | None
    content_type: str = "application/zip"
    presigned_url: str | None = None


class YankRequest(ApiModel):
    reason: str | None = Field(default=None, max_length=2000)


class LifecycleResponse(ApiModel):
    skill_id: int
    slug: str
    status: str
    hidden: bool


class VersionYankedResponse(ApiModel):
    skill_id: int
    version_id: int
    version: str
    status: str


PublishVisibility = Visibility
