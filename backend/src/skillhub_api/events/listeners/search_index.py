"""Keep ``skill_search_document`` in sync with skill state.

Triggered on:
  * ``SkillPublishedEvent`` — upsert the doc with fresh metadata.
  * ``SkillStatusChangedEvent`` — upsert on ACTIVE / ARCHIVED delete.
  * ``SkillVersionYankedEvent`` — re-upsert so ``latest_version_id``
    changes propagate (the doc stores no version id itself, but the
    status can flip if yanked was the latest).
"""

from __future__ import annotations

from skillhub_api.domain.events import (
    DomainEvent,
    SkillPublishedEvent,
    SkillStatusChangedEvent,
    SkillVersionYankedEvent,
)
from skillhub_api.events.bus import EventBus
from skillhub_api.infra.db.models.namespace import Namespace
from skillhub_api.infra.db.models.skill import Skill, SkillVersion
from skillhub_api.infra.db.session import AsyncSessionLocal
from skillhub_api.logging import get_logger
from skillhub_api.search.document import build_document
from skillhub_api.search.index import SearchIndexService

logger = get_logger(__name__)


async def _reindex_skill(skill_id: int) -> None:
    async with AsyncSessionLocal()() as session:
        skill = await session.get(Skill, skill_id)
        if skill is None:
            return
        namespace = await session.get(Namespace, skill.namespace_id)
        if namespace is None:
            return

        manifest: dict | None = None
        if skill.latest_version_id:
            version = await session.get(SkillVersion, skill.latest_version_id)
            if version is not None:
                manifest = version.manifest_json

        doc = build_document(
            skill_id=skill.id,
            namespace_id=skill.namespace_id,
            namespace_slug=namespace.slug,
            owner_id=skill.owner_id,
            slug=skill.slug,
            display_name=skill.display_name,
            summary=skill.summary,
            visibility=skill.visibility,
            status=skill.status,
            manifest=manifest,
        )
        await SearchIndexService(session).upsert(doc)
        await session.commit()


async def _remove_from_index(skill_id: int) -> None:
    async with AsyncSessionLocal()() as session:
        await SearchIndexService(session).remove(skill_id)
        await session.commit()


async def _on_published(event: DomainEvent) -> None:
    assert isinstance(event, SkillPublishedEvent)
    try:
        await _reindex_skill(event.skill_id)
    except Exception as exc:  # pragma: no cover — surfaced via structlog
        logger.error("search.reindex_failed", skill_id=event.skill_id, error=str(exc))


async def _on_status_changed(event: DomainEvent) -> None:
    assert isinstance(event, SkillStatusChangedEvent)
    try:
        if event.new_status == "ARCHIVED":
            await _remove_from_index(event.skill_id)
        else:
            await _reindex_skill(event.skill_id)
    except Exception as exc:  # pragma: no cover
        logger.error("search.status_change_failed", skill_id=event.skill_id, error=str(exc))


async def _on_yanked(event: DomainEvent) -> None:
    assert isinstance(event, SkillVersionYankedEvent)
    try:
        await _reindex_skill(event.skill_id)
    except Exception as exc:  # pragma: no cover
        logger.error("search.yank_reindex_failed", skill_id=event.skill_id, error=str(exc))


def register_search_listeners(bus: EventBus) -> None:
    bus.subscribe(SkillPublishedEvent, _on_published)
    bus.subscribe(SkillStatusChangedEvent, _on_status_changed)
    bus.subscribe(SkillVersionYankedEvent, _on_yanked)
