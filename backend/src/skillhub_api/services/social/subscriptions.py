"""Skill subscription service.

Maintains ``skill.subscription_count`` inline (same pattern as the Java
service): we increment/decrement directly inside the transaction so the
UI reflects the new count immediately, then emit an event for any
downstream listeners.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from skillhub_api.domain.events import SkillSubscribedEvent, SkillUnsubscribedEvent
from skillhub_api.errors import NotFoundError
from skillhub_api.events.bus import EventBus
from skillhub_api.infra.db.models.skill import Skill
from skillhub_api.infra.repositories.skill import SkillRepository
from skillhub_api.infra.repositories.social import SkillSubscriptionRepository


class SkillSubscriptionService:
    def __init__(self, session: AsyncSession, bus: EventBus) -> None:
        self._session = session
        self._bus = bus
        self._subs = SkillSubscriptionRepository(session)
        self._skills = SkillRepository(session)

    async def subscribe(self, *, skill_id: int, user_id: str) -> bool:
        skill = await self._skills.get(skill_id)
        if skill is None:
            raise NotFoundError("SKILL_NOT_FOUND", "skill not found")
        existing = await self._subs.find(skill_id, user_id)
        if existing is not None:
            return True
        await self._subs.add(skill_id, user_id)
        await self._session.execute(
            update(Skill)
            .where(Skill.id == skill_id)
            .values(subscription_count=Skill.subscription_count + 1)
        )
        await self._session.flush()
        self._bus.enqueue(
            SkillSubscribedEvent(occurred_at=datetime.now(UTC), skill_id=skill_id, user_id=user_id)
        )
        return True

    async def unsubscribe(self, *, skill_id: int, user_id: str) -> bool:
        existing = await self._subs.find(skill_id, user_id)
        if existing is None:
            return False
        await self._subs.remove(existing)
        await self._session.execute(
            update(Skill)
            .where(Skill.id == skill_id)
            .values(subscription_count=Skill.subscription_count - 1)
        )
        await self._session.flush()
        self._bus.enqueue(
            SkillUnsubscribedEvent(
                occurred_at=datetime.now(UTC), skill_id=skill_id, user_id=user_id
            )
        )
        return True

    async def is_subscribed(self, *, skill_id: int, user_id: str) -> bool:
        return (await self._subs.find(skill_id, user_id)) is not None
