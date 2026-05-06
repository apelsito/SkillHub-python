"""Star / favorite service.

Idempotent: starring twice is a no-op; unstarring when not starred is a
no-op. Rollup of ``skill.star_count`` is handled by the post-commit
event listener ([events/listeners/social.py](#)) so retries always
re-aggregate from the authoritative ``skill_star`` table.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from skillhub_api.domain.events import SkillStarredEvent, SkillUnstarredEvent
from skillhub_api.errors import NotFoundError
from skillhub_api.events.bus import EventBus
from skillhub_api.infra.repositories.skill import SkillRepository
from skillhub_api.infra.repositories.social import SkillStarRepository


class SkillStarService:
    def __init__(self, session: AsyncSession, bus: EventBus) -> None:
        self._session = session
        self._bus = bus
        self._stars = SkillStarRepository(session)
        self._skills = SkillRepository(session)

    async def star(self, *, skill_id: int, user_id: str) -> bool:
        skill = await self._skills.get(skill_id)
        if skill is None:
            raise NotFoundError("SKILL_NOT_FOUND", "skill not found")
        existing = await self._stars.find(skill_id, user_id)
        if existing is not None:
            return True
        await self._stars.add(skill_id, user_id)
        self._bus.enqueue(
            SkillStarredEvent(occurred_at=datetime.now(UTC), skill_id=skill_id, user_id=user_id)
        )
        return True

    async def unstar(self, *, skill_id: int, user_id: str) -> bool:
        existing = await self._stars.find(skill_id, user_id)
        if existing is None:
            return False
        await self._stars.remove(existing)
        self._bus.enqueue(
            SkillUnstarredEvent(occurred_at=datetime.now(UTC), skill_id=skill_id, user_id=user_id)
        )
        return True

    async def has_starred(self, *, skill_id: int, user_id: str) -> bool:
        return (await self._stars.find(skill_id, user_id)) is not None
