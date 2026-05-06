"""Star / rating / subscription repositories."""

from __future__ import annotations

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from skillhub_api.infra.db.models.social import SkillRating, SkillStar, SkillSubscription


class SkillStarRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find(self, skill_id: int, user_id: str) -> SkillStar | None:
        stmt = (
            select(SkillStar)
            .where(and_(SkillStar.skill_id == skill_id, SkillStar.user_id == user_id))
            .limit(1)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def add(self, skill_id: int, user_id: str) -> SkillStar:
        row = SkillStar(skill_id=skill_id, user_id=user_id)
        self._session.add(row)
        await self._session.flush()
        return row

    async def remove(self, row: SkillStar) -> None:
        await self._session.delete(row)
        await self._session.flush()

    async def count_for_skill(self, skill_id: int) -> int:
        stmt = select(func.count()).select_from(SkillStar).where(SkillStar.skill_id == skill_id)
        return int((await self._session.execute(stmt)).scalar_one())


class SkillRatingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find(self, skill_id: int, user_id: str) -> SkillRating | None:
        stmt = (
            select(SkillRating)
            .where(and_(SkillRating.skill_id == skill_id, SkillRating.user_id == user_id))
            .limit(1)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def upsert(self, skill_id: int, user_id: str, score: int) -> SkillRating:
        row = await self.find(skill_id, user_id)
        if row is None:
            row = SkillRating(skill_id=skill_id, user_id=user_id, score=score)
            self._session.add(row)
        else:
            row.score = score
        await self._session.flush()
        return row

    async def aggregate(self, skill_id: int) -> tuple[float, int]:
        stmt = select(func.coalesce(func.avg(SkillRating.score), 0.0), func.count()).where(
            SkillRating.skill_id == skill_id
        )
        row = (await self._session.execute(stmt)).one()
        return float(row[0] or 0.0), int(row[1] or 0)


class SkillSubscriptionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find(self, skill_id: int, user_id: str) -> SkillSubscription | None:
        stmt = (
            select(SkillSubscription)
            .where(
                and_(
                    SkillSubscription.skill_id == skill_id,
                    SkillSubscription.user_id == user_id,
                )
            )
            .limit(1)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def add(self, skill_id: int, user_id: str) -> SkillSubscription:
        row = SkillSubscription(skill_id=skill_id, user_id=user_id)
        self._session.add(row)
        await self._session.flush()
        return row

    async def remove(self, row: SkillSubscription) -> None:
        await self._session.delete(row)
        await self._session.flush()

    async def subscribers(self, skill_id: int) -> list[str]:
        stmt = select(SkillSubscription.user_id).where(SkillSubscription.skill_id == skill_id)
        return list((await self._session.execute(stmt)).scalars())

    async def count_for_skill(self, skill_id: int) -> int:
        stmt = (
            select(func.count())
            .select_from(SkillSubscription)
            .where(SkillSubscription.skill_id == skill_id)
        )
        return int((await self._session.execute(stmt)).scalar_one())
