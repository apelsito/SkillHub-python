"""Domain events published after a successful transaction.

Mirrors the Java ``domain/event/*`` package. Events are pure dataclasses —
no behavior — so they can be serialized, logged, or replayed without
pulling the ORM into listener code.

Listeners registered with the event bus consume these after the committing
transaction returns. If a listener raises, it is logged but does not roll
back the upstream commit — mirrors Spring's ``@TransactionalEventListener``
with ``AFTER_COMMIT`` phase.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class DomainEvent:
    """Marker base class — every event should carry an ``occurred_at`` ts."""

    occurred_at: datetime


# ---- Skill lifecycle ----


@dataclass(frozen=True, slots=True)
class SkillPublishedEvent(DomainEvent):
    skill_id: int
    version_id: int
    publisher_id: str


@dataclass(frozen=True, slots=True)
class SkillDownloadedEvent(DomainEvent):
    skill_id: int
    version_id: int


@dataclass(frozen=True, slots=True)
class SkillStatusChangedEvent(DomainEvent):
    skill_id: int
    new_status: str


@dataclass(frozen=True, slots=True)
class SkillVersionYankedEvent(DomainEvent):
    skill_id: int
    version_id: int
    actor_user_id: str


# ---- Review / promotion / report ----


@dataclass(frozen=True, slots=True)
class ReviewSubmittedEvent(DomainEvent):
    skill_id: int
    version_id: int
    review_id: int
    namespace_id: int
    submitter_id: str


@dataclass(frozen=True, slots=True)
class ReviewApprovedEvent(DomainEvent):
    skill_id: int
    version_id: int
    review_id: int
    reviewer_id: str
    submitter_id: str


@dataclass(frozen=True, slots=True)
class ReviewRejectedEvent(DomainEvent):
    skill_id: int
    version_id: int
    review_id: int
    reviewer_id: str
    submitter_id: str
    reason: str | None


@dataclass(frozen=True, slots=True)
class PromotionSubmittedEvent(DomainEvent):
    skill_id: int
    version_id: int
    promotion_id: int
    submitter_id: str


@dataclass(frozen=True, slots=True)
class PromotionApprovedEvent(DomainEvent):
    skill_id: int
    promotion_id: int
    reviewer_id: str
    submitter_id: str


@dataclass(frozen=True, slots=True)
class PromotionRejectedEvent(DomainEvent):
    skill_id: int
    promotion_id: int
    reviewer_id: str
    submitter_id: str
    reason: str | None


@dataclass(frozen=True, slots=True)
class ReportSubmittedEvent(DomainEvent):
    skill_id: int
    report_id: int
    reporter_id: str


@dataclass(frozen=True, slots=True)
class ReportResolvedEvent(DomainEvent):
    skill_id: int
    report_id: int
    reporter_id: str
    handler_id: str
    action: str


# ---- Social ----


@dataclass(frozen=True, slots=True)
class SkillStarredEvent(DomainEvent):
    skill_id: int
    user_id: str


@dataclass(frozen=True, slots=True)
class SkillUnstarredEvent(DomainEvent):
    skill_id: int
    user_id: str


@dataclass(frozen=True, slots=True)
class SkillRatedEvent(DomainEvent):
    skill_id: int
    user_id: str


@dataclass(frozen=True, slots=True)
class SkillSubscribedEvent(DomainEvent):
    skill_id: int
    user_id: str


@dataclass(frozen=True, slots=True)
class SkillUnsubscribedEvent(DomainEvent):
    skill_id: int
    user_id: str


# ---- Profile ----


@dataclass(frozen=True, slots=True)
class ProfileChangeSubmittedEvent(DomainEvent):
    user_id: str
    request_id: int


@dataclass(frozen=True, slots=True)
class ProfileChangeApprovedEvent(DomainEvent):
    user_id: str
    request_id: int
    reviewer_id: str


@dataclass(frozen=True, slots=True)
class ProfileChangeRejectedEvent(DomainEvent):
    user_id: str
    request_id: int
    reviewer_id: str
    reason: str | None
