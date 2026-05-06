"""Notification constants — categories, event types, default channels.

Kept in the domain layer so listeners, preferences, and the UI refer to
the same strings. Changing any value here is a contract break that must
be coordinated with the frontend.
"""

from __future__ import annotations

from enum import StrEnum


class Category(StrEnum):
    PUBLISH = "PUBLISH"
    REVIEW = "REVIEW"
    PROMOTION = "PROMOTION"
    REPORT = "REPORT"


class Channel(StrEnum):
    IN_APP = "IN_APP"


class EventType(StrEnum):
    SKILL_PUBLISHED = "SKILL_PUBLISHED"
    SUBSCRIPTION_NEW_VERSION = "SUBSCRIPTION_NEW_VERSION"
    SUBSCRIPTION_VERSION_YANKED = "SUBSCRIPTION_VERSION_YANKED"
    REVIEW_SUBMITTED = "REVIEW_SUBMITTED"
    REVIEW_APPROVED = "REVIEW_APPROVED"
    REVIEW_REJECTED = "REVIEW_REJECTED"
    PROMOTION_SUBMITTED = "PROMOTION_SUBMITTED"
    PROMOTION_APPROVED = "PROMOTION_APPROVED"
    PROMOTION_REJECTED = "PROMOTION_REJECTED"
    REPORT_SUBMITTED = "REPORT_SUBMITTED"
    REPORT_RESOLVED = "REPORT_RESOLVED"


DEFAULT_CATEGORIES: list[Category] = list(Category)
DEFAULT_CHANNELS: list[Channel] = [Channel.IN_APP]
