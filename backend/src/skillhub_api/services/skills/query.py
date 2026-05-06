"""Read-side services: list skills, get by slug, list versions, list files."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from skillhub_api.errors import NotFoundError
from skillhub_api.infra.db.models.skill import Skill, SkillFile, SkillVersion
from skillhub_api.infra.repositories.skill import (
    NamespaceRepository,
    SkillFileRepository,
    SkillRepository,
    SkillVersionRepository,
)


@dataclass(slots=True)
class Page[T]:
    items: list[T]
    total: int
    limit: int
    offset: int


class SkillQueryService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._namespaces = NamespaceRepository(session)
        self._skills = SkillRepository(session)
        self._versions = SkillVersionRepository(session)
        self._files = SkillFileRepository(session)

    async def list_skills(
        self,
        *,
        namespace_slug: str | None,
        limit: int,
        offset: int,
    ) -> Page[Skill]:
        namespace_id: int | None = None
        if namespace_slug is not None:
            ns = await self._namespaces.find_by_slug(namespace_slug)
            if ns is None:
                raise NotFoundError(
                    "NAMESPACE_NOT_FOUND", f"namespace {namespace_slug!r} not found"
                )
            namespace_id = ns.id
        rows, total = await self._skills.list_visible(
            namespace_id=namespace_id, limit=limit, offset=offset
        )
        return Page(items=rows, total=total, limit=limit, offset=offset)

    async def get_skill(self, namespace_slug: str, slug: str) -> Skill:
        ns = await self._namespaces.find_by_slug(namespace_slug)
        if ns is None:
            raise NotFoundError("NAMESPACE_NOT_FOUND", f"namespace {namespace_slug!r} not found")
        rows = await self._skills.find_by_slug(ns.id, slug)
        # With owner isolation, the same (namespace, slug) can yield multiple
        # skills (one per owner). The public endpoint returns the earliest
        # active, hidden-excluded row.
        for r in rows:
            if r.status == "ACTIVE" and not r.hidden:
                return r
        raise NotFoundError("SKILL_NOT_FOUND", f"{namespace_slug}/{slug} not found")

    async def list_versions(
        self, namespace_slug: str, slug: str, *, limit: int, offset: int
    ) -> Page[SkillVersion]:
        skill = await self.get_skill(namespace_slug, slug)
        rows, total = await self._versions.list_for_skill(skill.id, limit=limit, offset=offset)
        return Page(items=rows, total=total, limit=limit, offset=offset)

    async def get_version(
        self, namespace_slug: str, slug: str, version: str
    ) -> tuple[Skill, SkillVersion]:
        skill = await self.get_skill(namespace_slug, slug)
        row = await self._versions.find(skill.id, version)
        if row is None:
            raise NotFoundError(
                "VERSION_NOT_FOUND", f"version {version!r} not found on {namespace_slug}/{slug}"
            )
        return skill, row

    async def list_files(self, namespace_slug: str, slug: str, version: str) -> list[SkillFile]:
        _, version_row = await self.get_version(namespace_slug, slug, version)
        return await self._files.list_for_version(version_row.id)
