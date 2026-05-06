"""Notification fan-out listener.

Maps governance/publish/report events to rows in ``notification`` and
broadcasts a JSON payload on the Redis channel so any SSE connection
(in this pod or another) picks it up. The mapping matches the Java
``NotificationEventListener`` table: who gets notified and what
``category``/``event_type`` the row carries.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from skillhub_api.domain.events import (
    DomainEvent,
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
from skillhub_api.domain.notifications import Category, EventType
from skillhub_api.events.bus import EventBus
from skillhub_api.infra.db.models.auth import Role, UserRoleBinding
from skillhub_api.infra.db.models.namespace import NamespaceMember
from skillhub_api.infra.db.session import AsyncSessionLocal
from skillhub_api.infra.repositories.notification import NotificationRepository
from skillhub_api.infra.repositories.social import SkillSubscriptionRepository
from skillhub_api.logging import get_logger
from skillhub_api.sse.manager import redis_broadcast

logger = get_logger(__name__)


async def _namespace_admins(session: AsyncSession, namespace_id: int) -> list[str]:
    stmt = select(NamespaceMember.user_id).where(
        NamespaceMember.namespace_id == namespace_id,
        NamespaceMember.role.in_(("OWNER", "ADMIN")),
    )
    return list((await session.execute(stmt)).scalars())


async def _platform_skill_admins(session: AsyncSession) -> list[str]:
    stmt = (
        select(UserRoleBinding.user_id)
        .join(Role, Role.id == UserRoleBinding.role_id)
        .where(Role.code.in_(("SUPER_ADMIN", "SKILL_ADMIN")))
    )
    return list((await session.execute(stmt)).scalars())


async def _persist_and_broadcast(
    session: AsyncSession,
    *,
    recipient_id: str,
    category: Category,
    event_type: EventType,
    title: str,
    body: dict,
    entity_type: str | None = None,
    entity_id: int | None = None,
) -> None:
    repo = NotificationRepository(session)
    row = await repo.create(
        recipient_id=recipient_id,
        category=category.value,
        event_type=event_type.value,
        title=title,
        body_json=json.dumps(body) if body else None,
        entity_type=entity_type,
        entity_id=entity_id,
    )
    payload = {
        "id": row.id,
        "category": row.category,
        "event_type": row.event_type,
        "title": row.title,
        "body": body,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "created_at": row.created_at.isoformat().replace("+00:00", "Z")
        if row.created_at
        else datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }
    await redis_broadcast(recipient_id=recipient_id, payload=payload)


async def _skill_display(session: AsyncSession, skill_id: int) -> tuple[str, str]:
    row = (
        await session.execute(
            text(
                "SELECT s.display_name, s.slug, n.slug FROM skill s "
                "JOIN namespace n ON n.id = s.namespace_id "
                "WHERE s.id = :id"
            ),
            {"id": skill_id},
        )
    ).one_or_none()
    if row is None:
        return "", ""
    display_name, slug, ns_slug = row
    return display_name or slug or "", f"{ns_slug}/{slug}"


async def _on_published(event: DomainEvent) -> None:
    assert isinstance(event, SkillPublishedEvent)
    async with AsyncSessionLocal()() as session:
        display, path = await _skill_display(session, event.skill_id)
        # 1) Publisher gets a "published" notification.
        await _persist_and_broadcast(
            session,
            recipient_id=event.publisher_id,
            category=Category.PUBLISH,
            event_type=EventType.SKILL_PUBLISHED,
            title=f"Skill published: {display}",
            body={"skill_id": event.skill_id, "version_id": event.version_id, "path": path},
            entity_type="skill",
            entity_id=event.skill_id,
        )
        # 2) Subscribers (minus publisher) get a "new version" notification.
        sub_repo = SkillSubscriptionRepository(session)
        for user_id in await sub_repo.subscribers(event.skill_id):
            if user_id == event.publisher_id:
                continue
            await _persist_and_broadcast(
                session,
                recipient_id=user_id,
                category=Category.PUBLISH,
                event_type=EventType.SUBSCRIPTION_NEW_VERSION,
                title=f"New version of {display}",
                body={
                    "skill_id": event.skill_id,
                    "version_id": event.version_id,
                    "path": path,
                },
                entity_type="skill",
                entity_id=event.skill_id,
            )
        await session.commit()


async def _on_version_yanked(event: DomainEvent) -> None:
    assert isinstance(event, SkillVersionYankedEvent)
    async with AsyncSessionLocal()() as session:
        display, path = await _skill_display(session, event.skill_id)
        sub_repo = SkillSubscriptionRepository(session)
        for user_id in await sub_repo.subscribers(event.skill_id):
            if user_id == event.actor_user_id:
                continue
            await _persist_and_broadcast(
                session,
                recipient_id=user_id,
                category=Category.PUBLISH,
                event_type=EventType.SUBSCRIPTION_VERSION_YANKED,
                title=f"Version yanked from {display}",
                body={"skill_id": event.skill_id, "version_id": event.version_id, "path": path},
                entity_type="skill",
                entity_id=event.skill_id,
            )
        await session.commit()


async def _on_review_submitted(event: DomainEvent) -> None:
    assert isinstance(event, ReviewSubmittedEvent)
    async with AsyncSessionLocal()() as session:
        display, path = await _skill_display(session, event.skill_id)
        for user_id in await _namespace_admins(session, event.namespace_id):
            await _persist_and_broadcast(
                session,
                recipient_id=user_id,
                category=Category.REVIEW,
                event_type=EventType.REVIEW_SUBMITTED,
                title=f"Review requested for {display}",
                body={"skill_id": event.skill_id, "review_id": event.review_id, "path": path},
                entity_type="review",
                entity_id=event.review_id,
            )
        await session.commit()


async def _on_review_decision(event: DomainEvent) -> None:
    assert isinstance(event, ReviewApprovedEvent | ReviewRejectedEvent)
    async with AsyncSessionLocal()() as session:
        display, path = await _skill_display(session, event.skill_id)
        if isinstance(event, ReviewApprovedEvent):
            title = f"Review approved for {display}"
            etype = EventType.REVIEW_APPROVED
            body = {"skill_id": event.skill_id, "review_id": event.review_id, "path": path}
        else:
            title = f"Review rejected for {display}"
            etype = EventType.REVIEW_REJECTED
            body = {
                "skill_id": event.skill_id,
                "review_id": event.review_id,
                "reason": event.reason,
                "path": path,
            }
        await _persist_and_broadcast(
            session,
            recipient_id=event.submitter_id,
            category=Category.REVIEW,
            event_type=etype,
            title=title,
            body=body,
            entity_type="review",
            entity_id=event.review_id,
        )
        await session.commit()


async def _on_promotion(event: DomainEvent) -> None:
    async with AsyncSessionLocal()() as session:
        if isinstance(event, PromotionSubmittedEvent):
            display, path = await _skill_display(session, event.skill_id)
            for user_id in await _platform_skill_admins(session):
                await _persist_and_broadcast(
                    session,
                    recipient_id=user_id,
                    category=Category.PROMOTION,
                    event_type=EventType.PROMOTION_SUBMITTED,
                    title=f"Promotion requested for {display}",
                    body={
                        "skill_id": event.skill_id,
                        "promotion_id": event.promotion_id,
                        "path": path,
                    },
                    entity_type="promotion",
                    entity_id=event.promotion_id,
                )
        elif isinstance(event, PromotionApprovedEvent | PromotionRejectedEvent):
            display, path = await _skill_display(session, event.skill_id)
            if isinstance(event, PromotionApprovedEvent):
                etype = EventType.PROMOTION_APPROVED
                title = f"Promotion approved for {display}"
                body = {
                    "skill_id": event.skill_id,
                    "promotion_id": event.promotion_id,
                    "path": path,
                }
            else:
                etype = EventType.PROMOTION_REJECTED
                title = f"Promotion rejected for {display}"
                body = {
                    "skill_id": event.skill_id,
                    "promotion_id": event.promotion_id,
                    "reason": event.reason,
                    "path": path,
                }
            await _persist_and_broadcast(
                session,
                recipient_id=event.submitter_id,
                category=Category.PROMOTION,
                event_type=etype,
                title=title,
                body=body,
                entity_type="promotion",
                entity_id=event.promotion_id,
            )
        await session.commit()


async def _on_report(event: DomainEvent) -> None:
    async with AsyncSessionLocal()() as session:
        display, path = await _skill_display(session, event.skill_id)
        if isinstance(event, ReportSubmittedEvent):
            for user_id in await _platform_skill_admins(session):
                await _persist_and_broadcast(
                    session,
                    recipient_id=user_id,
                    category=Category.REPORT,
                    event_type=EventType.REPORT_SUBMITTED,
                    title=f"Report filed against {display}",
                    body={
                        "skill_id": event.skill_id,
                        "report_id": event.report_id,
                        "path": path,
                    },
                    entity_type="report",
                    entity_id=event.report_id,
                )
        elif isinstance(event, ReportResolvedEvent):
            await _persist_and_broadcast(
                session,
                recipient_id=event.reporter_id,
                category=Category.REPORT,
                event_type=EventType.REPORT_RESOLVED,
                title=f"Your report was {event.action.lower()}",
                body={
                    "skill_id": event.skill_id,
                    "report_id": event.report_id,
                    "action": event.action,
                    "path": path,
                },
                entity_type="report",
                entity_id=event.report_id,
            )
        await session.commit()


def register_notification_listeners(bus: EventBus) -> None:
    bus.subscribe(SkillPublishedEvent, _on_published)
    bus.subscribe(SkillVersionYankedEvent, _on_version_yanked)
    bus.subscribe(ReviewSubmittedEvent, _on_review_submitted)
    bus.subscribe(ReviewApprovedEvent, _on_review_decision)
    bus.subscribe(ReviewRejectedEvent, _on_review_decision)
    bus.subscribe(PromotionSubmittedEvent, _on_promotion)
    bus.subscribe(PromotionApprovedEvent, _on_promotion)
    bus.subscribe(PromotionRejectedEvent, _on_promotion)
    bus.subscribe(ReportSubmittedEvent, _on_report)
    bus.subscribe(ReportResolvedEvent, _on_report)
