"""DTOs for notification endpoints."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from skillhub_api.schemas.base import ApiModel


class NotificationResponse(ApiModel):
    id: int
    category: str
    event_type: str
    title: str
    body_json: str | None
    entity_type: str | None
    entity_id: int | None
    status: str
    created_at: datetime
    read_at: datetime | None


class NotificationListResponse(ApiModel):
    items: list[NotificationResponse]
    total: int
    limit: int
    offset: int
    page: int | None = None
    size: int | None = None


class UnreadCountResponse(ApiModel):
    count: int


class MarkAllReadResponse(ApiModel):
    updated: int


class PreferenceEntry(ApiModel):
    category: str
    channel: str
    enabled: bool


class PreferenceListResponse(ApiModel):
    preferences: list[PreferenceEntry]


class PreferenceBulkUpdate(ApiModel):
    preferences: list[PreferenceEntry] = Field(min_length=1)
