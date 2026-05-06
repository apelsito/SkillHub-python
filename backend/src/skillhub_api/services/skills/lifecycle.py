"""Skill lifecycle mutations: archive/unarchive + version yank.

Ports the subset of ``SkillLifecycleController`` that does not depend on
the review workflow (reviews land in Phase 4). Archive/unarchive are full
parity; version-yank is partial (no compensation task integration yet).
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from skillhub_api.errors import ConflictError, ForbiddenError, NotFoundError
from skillhub_api.infra.db.models.skill import Skill, SkillVersion
from skillhub_api.infra.repositories.skill import NamespaceRepository, SkillRepository
from skillhub_api.services.skills.query import SkillQueryService


class SkillLifecycleService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._query = SkillQueryService(session)

    async def archive(self, *, namespace_slug: str, slug: str, actor_id: str) -> Skill:
        skill = await self._get_owned_skill(namespace_slug, slug, actor_id)
        if skill.status == "ARCHIVED":
            return skill
        skill.status = "ARCHIVED"
        skill.hidden = True
        skill.hidden_at = datetime.now(UTC)
        skill.hidden_by = actor_id
        skill.updated_by = actor_id
        await self._session.flush()
        return skill

    async def unarchive(self, *, namespace_slug: str, slug: str, actor_id: str) -> Skill:
        skill = await self._get_owned_skill(namespace_slug, slug, actor_id)
        if skill.status == "ACTIVE":
            return skill
        skill.status = "ACTIVE"
        skill.hidden = False
        skill.hidden_at = None
        skill.hidden_by = None
        skill.updated_by = actor_id
        await self._session.flush()
        return skill

    async def yank_version(
        self,
        *,
        namespace_slug: str,
        slug: str,
        version: str,
        reason: str | None,
        actor_id: str,
    ) -> SkillVersion:
        skill = await self._get_owned_skill(namespace_slug, slug, actor_id)
        _, row = await self._query.get_version(namespace_slug, slug, version)
        if row.status == "YANKED":
            raise ConflictError("ALREADY_YANKED", "version already yanked")
        row.status = "YANKED"
        row.yanked_at = datetime.now(UTC)
        row.yanked_by = actor_id
        row.yank_reason = reason
        row.download_ready = False
        if skill.latest_version_id == row.id:
            skill.latest_version_id = None
        await self._session.flush()
        return row

    async def _get_owned_skill(self, namespace_slug: str, slug: str, actor_id: str) -> Skill:
        namespace = await NamespaceRepository(self._session).find_by_slug(namespace_slug)
        if namespace is None:
            raise NotFoundError("NAMESPACE_NOT_FOUND", f"namespace {namespace_slug!r} not found")
        skill = await SkillRepository(self._session).find_owned(namespace.id, slug, actor_id)
        if skill is None:
            raise NotFoundError("SKILL_NOT_FOUND", f"{namespace_slug}/{slug} not found")
        if skill.owner_id != actor_id:
            # Admin fallback lands in Phase 7 — for now only the owner can
            # archive/yank.
            raise ForbiddenError("NOT_SKILL_OWNER", "only the skill owner can perform this action")
        if skill is None:  # pragma: no cover — get_skill already raises
            raise NotFoundError("SKILL_NOT_FOUND", f"{namespace_slug}/{slug} not found")
        return skill
