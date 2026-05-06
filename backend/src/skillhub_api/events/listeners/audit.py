"""Audit log listener — writes a row to ``audit_log`` for every governance event.

Runs in its own async DB session (post-commit) so audit writes are
independent of the upstream transaction.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime

from skillhub_api.domain.events import (
    DomainEvent,
    ProfileChangeApprovedEvent,
    ProfileChangeRejectedEvent,
    ProfileChangeSubmittedEvent,
    PromotionApprovedEvent,
    PromotionRejectedEvent,
    PromotionSubmittedEvent,
    ReportResolvedEvent,
    ReportSubmittedEvent,
    ReviewApprovedEvent,
    ReviewRejectedEvent,
    ReviewSubmittedEvent,
    SkillPublishedEvent,
    SkillVersionYankedEvent,
)
from skillhub_api.events.bus import EventBus
from skillhub_api.infra.db.models.audit import AuditLog
from skillhub_api.infra.db.session import AsyncSessionLocal

_ACTIONS: dict[type[DomainEvent], str] = {
    SkillPublishedEvent: "skill.published",
    SkillVersionYankedEvent: "skill.version_yanked",
    ReviewSubmittedEvent: "review.submitted",
    ReviewApprovedEvent: "review.approved",
    ReviewRejectedEvent: "review.rejected",
    PromotionSubmittedEvent: "promotion.submitted",
    PromotionApprovedEvent: "promotion.approved",
    PromotionRejectedEvent: "promotion.rejected",
    ReportSubmittedEvent: "report.submitted",
    ReportResolvedEvent: "report.resolved",
    ProfileChangeSubmittedEvent: "profile.change_submitted",
    ProfileChangeApprovedEvent: "profile.change_approved",
    ProfileChangeRejectedEvent: "profile.change_rejected",
}


def _payload(event: DomainEvent) -> tuple[str | None, int | None, str | None, dict]:
    """Extract (actor, target_id, target_type, extra) from an event."""
    extra = {k: v for k, v in asdict(event).items() if k != "occurred_at"}

    actor: str | None = None
    for key in (
        "reviewer_id",
        "handler_id",
        "actor_user_id",
        "publisher_id",
        "submitter_id",
        "reporter_id",
        "user_id",
    ):
        if key in extra and isinstance(extra[key], str):
            actor = extra[key]
            break

    target_id: int | None = None
    target_type: str | None = None
    if "skill_id" in extra:
        target_id = extra["skill_id"]
        target_type = "skill"
    elif "request_id" in extra:
        target_id = extra["request_id"]
        target_type = "profile_change_request"

    return actor, target_id, target_type, extra


async def _write_audit(event: DomainEvent) -> None:
    action = _ACTIONS.get(type(event))
    if action is None:
        return
    actor, target_id, target_type, extra = _payload(event)
    async with AsyncSessionLocal()() as session:
        session.add(
            AuditLog(
                actor_user_id=actor,
                action=action,
                target_type=target_type,
                target_id=target_id,
                detail_json=extra,
                created_at=datetime.now(UTC),
            )
        )
        await session.commit()


def register_audit_listeners(bus: EventBus) -> None:
    for event_type in _ACTIONS:
        bus.subscribe(event_type, _write_audit)
