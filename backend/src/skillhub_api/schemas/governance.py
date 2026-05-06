"""DTOs for governance endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from skillhub_api.schemas.base import ApiModel


class ReviewSummary(ApiModel):
    id: int
    skill_version_id: int
    namespace_id: int
    status: str
    submitted_by: str
    reviewed_by: str | None
    review_comment: str | None
    submitted_at: datetime
    reviewed_at: datetime | None


class ReviewListResponse(ApiModel):
    items: list[ReviewSummary]
    total: int
    limit: int
    offset: int
    page: int | None = None
    size: int | None = None


class ReviewSubmitRequest(ApiModel):
    skill_version_id: int


class ReviewApproveRequest(ApiModel):
    comment: str | None = Field(default=None, max_length=2000)


class ReviewRejectRequest(ApiModel):
    reason: str = Field(min_length=1, max_length=2000)


class SkillReportSummary(ApiModel):
    id: int
    skill_id: int
    namespace_id: int
    reporter_id: str
    reason: str
    details: str | None
    status: str
    handled_by: str | None
    handle_comment: str | None
    created_at: datetime
    handled_at: datetime | None


class SkillReportListResponse(ApiModel):
    items: list[SkillReportSummary]
    total: int
    limit: int
    offset: int
    page: int | None = None
    size: int | None = None


class SkillReportCreate(ApiModel):
    reason: str = Field(min_length=1, max_length=200)
    details: str | None = Field(default=None, max_length=2000)


class SkillReportHandle(ApiModel):
    action: str = Field(pattern=r"^(DISMISSED|HIDDEN|REMOVED)$")
    comment: str | None = Field(default=None, max_length=2000)


class AuditEntry(ApiModel):
    id: int
    actor_user_id: str | None
    action: str
    target_type: str | None
    target_id: int | None
    detail_json: dict[str, Any] | None
    created_at: datetime


class AuditListResponse(ApiModel):
    items: list[AuditEntry]
    total: int
    limit: int
    offset: int


class ProfileChangeSubmit(ApiModel):
    changes: dict[str, Any] = Field(min_length=1)


class ProfileChangeSummary(ApiModel):
    id: int
    user_id: str
    changes: dict[str, Any]
    old_values: dict[str, Any] | None
    status: str
    reviewer_id: str | None
    review_comment: str | None
    created_at: datetime
    reviewed_at: datetime | None


class ProfileChangeReject(ApiModel):
    reason: str = Field(min_length=1, max_length=2000)
