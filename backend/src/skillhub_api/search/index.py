"""Upsert/delete rows in ``skill_search_document``.

Does not build the document itself — callers pass a
``SkillSearchDocumentInput`` from ``skillhub_api.search.document``. The
UPSERT pattern is: lookup by ``skill_id`` (unique), update if present,
insert otherwise. No delete-then-insert (which would burn GIN index
cycles).
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from skillhub_api.infra.db.models.search import SkillSearchDocument
from skillhub_api.search.document import SkillSearchDocumentInput


class SearchIndexService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(self, doc: SkillSearchDocumentInput) -> None:
        existing = (
            await self._session.execute(
                select(SkillSearchDocument).where(SkillSearchDocument.skill_id == doc.skill_id)
            )
        ).scalar_one_or_none()

        now = datetime.now(UTC)
        if existing is None:
            self._session.add(
                SkillSearchDocument(
                    skill_id=doc.skill_id,
                    namespace_id=doc.namespace_id,
                    namespace_slug=doc.namespace_slug,
                    owner_id=doc.owner_id,
                    title=doc.title,
                    summary=doc.summary,
                    keywords=doc.keywords,
                    search_text=doc.search_text,
                    semantic_vector=doc.semantic_vector,
                    visibility=doc.visibility,
                    status=doc.status,
                    updated_at=now,
                )
            )
        else:
            existing.namespace_id = doc.namespace_id
            existing.namespace_slug = doc.namespace_slug
            existing.owner_id = doc.owner_id
            existing.title = doc.title
            existing.summary = doc.summary
            existing.keywords = doc.keywords
            existing.search_text = doc.search_text
            existing.semantic_vector = doc.semantic_vector
            existing.visibility = doc.visibility
            existing.status = doc.status
            existing.updated_at = now

        await self._session.flush()

    async def remove(self, skill_id: int) -> None:
        await self._session.execute(
            delete(SkillSearchDocument).where(SkillSearchDocument.skill_id == skill_id)
        )
        await self._session.flush()
