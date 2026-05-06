"""Label administration service.

Owns the invariants:
  * ``max_definitions`` total label_definition rows (default 100)
  * ``max_per_skill`` labels attached to any one skill (default 10)
  * translations are per-locale upserts (unique(label_id, locale))
"""

from __future__ import annotations

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from skillhub_api.errors import ConflictError, NotFoundError
from skillhub_api.infra.db.models.label import (
    LabelDefinition,
    LabelTranslation,
    SkillLabel,
)
from skillhub_api.infra.repositories.label import (
    LabelDefinitionRepository,
    LabelTranslationRepository,
    SkillLabelRepository,
)
from skillhub_api.settings import get_settings


class LabelDefinitionService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._defs = LabelDefinitionRepository(session)
        self._translations = LabelTranslationRepository(session)

    async def list_visible(self) -> list[tuple[LabelDefinition, list[LabelTranslation]]]:
        defs = await self._defs.list_visible()
        trans_by_label = await self._translations.list_for_labels([d.id for d in defs])
        return [(d, trans_by_label.get(d.id, [])) for d in defs]

    async def list_all(self) -> list[tuple[LabelDefinition, list[LabelTranslation]]]:
        defs = await self._defs.list_all()
        trans_by_label = await self._translations.list_for_labels([d.id for d in defs])
        return [(d, trans_by_label.get(d.id, [])) for d in defs]

    async def create(
        self,
        *,
        slug: str,
        type_: str,
        visible_in_filter: bool,
        sort_order: int,
        translations: list[dict],
        created_by: str,
    ) -> tuple[LabelDefinition, list[LabelTranslation]]:
        settings = get_settings()
        if await self._defs.count() >= settings.label_max_definitions:
            raise ConflictError(
                "LABEL_LIMIT_REACHED",
                f"max {settings.label_max_definitions} label definitions",
            )
        if await self._defs.find_by_slug(slug) is not None:
            raise ConflictError("LABEL_SLUG_TAKEN", f"slug {slug!r} already used")

        row = LabelDefinition(
            slug=slug,
            type=type_,
            visible_in_filter=visible_in_filter,
            sort_order=sort_order,
            created_by=created_by,
        )
        self._session.add(row)
        await self._session.flush()
        trans = await self._replace_translations(row.id, translations)
        return row, trans

    async def update(
        self,
        slug: str,
        *,
        type_: str | None,
        visible_in_filter: bool | None,
        sort_order: int | None,
        translations: list[dict] | None,
    ) -> tuple[LabelDefinition, list[LabelTranslation]]:
        row = await self._defs.find_by_slug(slug)
        if row is None:
            raise NotFoundError("LABEL_NOT_FOUND", f"label {slug!r} not found")
        if type_ is not None:
            row.type = type_
        if visible_in_filter is not None:
            row.visible_in_filter = visible_in_filter
        if sort_order is not None:
            row.sort_order = sort_order
        await self._session.flush()
        if translations is not None:
            trans = await self._replace_translations(row.id, translations)
        else:
            trans = await self._translations.list_for_label(row.id)
        return row, trans

    async def delete(self, slug: str) -> None:
        row = await self._defs.find_by_slug(slug)
        if row is None:
            raise NotFoundError("LABEL_NOT_FOUND", f"label {slug!r} not found")
        await self._session.delete(row)  # cascades to translations + skill_label
        await self._session.flush()

    async def update_sort_order(
        self, entries: list[dict]
    ) -> list[tuple[LabelDefinition, list[LabelTranslation]]]:
        for entry in entries:
            row = await self._defs.find_by_slug(entry["slug"])
            if row is None:
                raise NotFoundError("LABEL_NOT_FOUND", f"label {entry['slug']!r} not found")
            row.sort_order = int(entry["sort_order"])
        await self._session.flush()
        return await self.list_all()

    async def _replace_translations(
        self, label_id: int, translations: list[dict]
    ) -> list[LabelTranslation]:
        # Bulk replace: delete existing, insert new. Cheaper than per-locale
        # upsert when the request is the full desired state (matches the
        # Java ``LabelAdminAppService.replaceTranslations``).
        await self._session.execute(
            delete(LabelTranslation).where(LabelTranslation.label_id == label_id)
        )
        new_rows = [
            LabelTranslation(
                label_id=label_id,
                locale=t["locale"],
                display_name=t["display_name"],
            )
            for t in translations
        ]
        for r in new_rows:
            self._session.add(r)
        await self._session.flush()
        return new_rows


class SkillLabelService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._defs = LabelDefinitionRepository(session)
        self._skill_labels = SkillLabelRepository(session)

    async def attach(
        self, *, skill_id: int, label_slug: str, actor_id: str
    ) -> tuple[SkillLabel, LabelDefinition]:
        settings = get_settings()
        definition = await self._defs.find_by_slug(label_slug)
        if definition is None:
            raise NotFoundError("LABEL_NOT_FOUND", f"label {label_slug!r} not found")
        existing = await self._skill_labels.find(skill_id, definition.id)
        if existing is not None:
            return existing, definition
        if await self._skill_labels.count_for_skill(skill_id) >= settings.label_max_per_skill:
            raise ConflictError(
                "LABEL_LIMIT_REACHED",
                f"skill already has the maximum of {settings.label_max_per_skill} labels",
            )
        row = SkillLabel(skill_id=skill_id, label_id=definition.id, created_by=actor_id)
        self._session.add(row)
        await self._session.flush()
        return row, definition

    async def detach(self, *, skill_id: int, label_slug: str) -> None:
        definition = await self._defs.find_by_slug(label_slug)
        if definition is None:
            return
        row = await self._skill_labels.find(skill_id, definition.id)
        if row is None:
            return
        await self._session.delete(row)
        await self._session.flush()

    async def list_for_skill(self, skill_id: int) -> list[tuple[SkillLabel, LabelDefinition]]:
        return await self._skill_labels.list_for_skill(skill_id)
