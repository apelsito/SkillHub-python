"""Label repositories."""

from __future__ import annotations

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from skillhub_api.infra.db.models.label import LabelDefinition, LabelTranslation, SkillLabel


class LabelDefinitionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def count(self) -> int:
        return int(
            (
                await self._session.execute(select(func.count()).select_from(LabelDefinition))
            ).scalar_one()
        )

    async def list_all(self) -> list[LabelDefinition]:
        stmt = select(LabelDefinition).order_by(
            LabelDefinition.sort_order.asc(), LabelDefinition.id.asc()
        )
        return list((await self._session.execute(stmt)).scalars())

    async def list_visible(self) -> list[LabelDefinition]:
        stmt = (
            select(LabelDefinition)
            .where(LabelDefinition.visible_in_filter.is_(True))
            .order_by(LabelDefinition.sort_order.asc(), LabelDefinition.id.asc())
        )
        return list((await self._session.execute(stmt)).scalars())

    async def find_by_slug(self, slug: str) -> LabelDefinition | None:
        stmt = select(LabelDefinition).where(LabelDefinition.slug == slug).limit(1)
        return (await self._session.execute(stmt)).scalar_one_or_none()


class LabelTranslationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_label(self, label_id: int) -> list[LabelTranslation]:
        stmt = select(LabelTranslation).where(LabelTranslation.label_id == label_id)
        return list((await self._session.execute(stmt)).scalars())

    async def list_for_labels(self, label_ids: list[int]) -> dict[int, list[LabelTranslation]]:
        if not label_ids:
            return {}
        stmt = select(LabelTranslation).where(LabelTranslation.label_id.in_(label_ids))
        rows = list((await self._session.execute(stmt)).scalars())
        by_label: dict[int, list[LabelTranslation]] = {}
        for r in rows:
            by_label.setdefault(r.label_id, []).append(r)
        return by_label


class SkillLabelRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def count_for_skill(self, skill_id: int) -> int:
        return int(
            (
                await self._session.execute(
                    select(func.count())
                    .select_from(SkillLabel)
                    .where(SkillLabel.skill_id == skill_id)
                )
            ).scalar_one()
        )

    async def find(self, skill_id: int, label_id: int) -> SkillLabel | None:
        stmt = (
            select(SkillLabel)
            .where(and_(SkillLabel.skill_id == skill_id, SkillLabel.label_id == label_id))
            .limit(1)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list_for_skill(self, skill_id: int) -> list[tuple[SkillLabel, LabelDefinition]]:
        stmt = (
            select(SkillLabel, LabelDefinition)
            .join(LabelDefinition, LabelDefinition.id == SkillLabel.label_id)
            .where(SkillLabel.skill_id == skill_id)
            .order_by(LabelDefinition.sort_order.asc(), LabelDefinition.id.asc())
        )
        return list((await self._session.execute(stmt)).all())
