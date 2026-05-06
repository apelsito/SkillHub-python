"""Skill rating service (upsert 1-5 score)."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from skillhub_api.domain.events import SkillRatedEvent
from skillhub_api.errors import ConflictError, NotFoundError
from skillhub_api.events.bus import EventBus
from skillhub_api.infra.db.models.social import SkillRating
from skillhub_api.infra.repositories.skill import SkillRepository
from skillhub_api.infra.repositories.social import SkillRatingRepository


class SkillRatingService:
    def __init__(self, session: AsyncSession, bus: EventBus) -> None:
        self._session = session
        self._bus = bus
        self._ratings = SkillRatingRepository(session)
        self._skills = SkillRepository(session)

    async def rate(self, *, skill_id: int, user_id: str, score: int) -> SkillRating:
        if not 1 <= score <= 5:
            raise ConflictError("INVALID_SCORE", "score must be between 1 and 5")
        skill = await self._skills.get(skill_id)
        if skill is None:
            raise NotFoundError("SKILL_NOT_FOUND", "skill not found")
        row = await self._ratings.upsert(skill_id, user_id, score)
        self._bus.enqueue(
            SkillRatedEvent(
                occurred_at=datetime.now(UTC),
                skill_id=skill_id,
                user_id=user_id,
            )
        )
        return row

    async def get_mine(self, *, skill_id: int, user_id: str) -> SkillRating | None:
        return await self._ratings.find(skill_id, user_id)
