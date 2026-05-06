"""Rebuild ``skill_search_document`` from scratch.

Used by the admin ``scripts/rebuild_search_index.py`` entry point and by
the ``SKILLHUB_SEARCH_REBUILD_ON_STARTUP=true`` lifecycle hook. UPSERTs
every ACTIVE skill — does not delete existing rows, so running while the
service is live is safe.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from skillhub_api.infra.db.models.namespace import Namespace
from skillhub_api.infra.db.models.skill import Skill, SkillVersion
from skillhub_api.search.document import build_document
from skillhub_api.search.index import SearchIndexService


async def rebuild_all(session: AsyncSession, *, batch_size: int = 100) -> int:
    """Rebuild the entire search index. Returns the number of docs upserted."""
    index_svc = SearchIndexService(session)
    stmt = select(Skill).where(Skill.status == "ACTIVE").execution_options(yield_per=batch_size)
    count = 0
    stream = await session.stream(stmt)
    async for skill in stream.scalars():
        namespace = await session.get(Namespace, skill.namespace_id)
        if namespace is None:
            continue
        manifest = None
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
        await index_svc.upsert(doc)
        count += 1
    await session.commit()
    return count
