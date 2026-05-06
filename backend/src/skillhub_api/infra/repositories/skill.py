"""Skill aggregate repositories."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from skillhub_api.infra.db.models.namespace import Namespace
from skillhub_api.infra.db.models.skill import Skill, SkillFile, SkillVersion


class NamespaceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_by_slug(self, slug: str) -> Namespace | None:
        stmt = select(Namespace).where(Namespace.slug == slug).limit(1)
        return (await self._session.execute(stmt)).scalar_one_or_none()


class SkillRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_owned(self, namespace_id: int, slug: str, owner_id: str) -> Skill | None:
        stmt = (
            select(Skill)
            .where(Skill.namespace_id == namespace_id)
            .where(Skill.slug == slug)
            .where(Skill.owner_id == owner_id)
            .limit(1)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def find_by_slug(self, namespace_id: int, slug: str) -> list[Skill]:
        """Return all skill rows for a (namespace, slug) pair across owners.

        Multiple owners can register distinct skills under the same slug —
        the UNIQUE constraint is ``(namespace_id, slug, owner_id)``.
        """
        stmt = (
            select(Skill)
            .where(Skill.namespace_id == namespace_id)
            .where(Skill.slug == slug)
            .order_by(Skill.created_at.asc())
        )
        return list((await self._session.execute(stmt)).scalars())

    async def get(self, skill_id: int) -> Skill | None:
        return await self._session.get(Skill, skill_id)

    async def create(
        self,
        *,
        namespace_id: int,
        slug: str,
        display_name: str | None,
        summary: str | None,
        owner_id: str,
        visibility: str,
        created_by: str,
    ) -> Skill:
        skill = Skill(
            namespace_id=namespace_id,
            slug=slug,
            display_name=display_name,
            summary=summary,
            owner_id=owner_id,
            visibility=visibility,
            created_by=created_by,
            updated_by=created_by,
        )
        self._session.add(skill)
        await self._session.flush()
        return skill

    async def list_visible(
        self, *, namespace_id: int | None, limit: int, offset: int
    ) -> tuple[list[Skill], int]:
        base = select(Skill).where(Skill.status == "ACTIVE").where(Skill.hidden.is_(False))
        if namespace_id is not None:
            base = base.where(Skill.namespace_id == namespace_id)
        total_stmt = select(func.count()).select_from(base.subquery())
        total = (await self._session.execute(total_stmt)).scalar_one()
        page_stmt = (
            base.order_by(Skill.updated_at.desc(), Skill.id.desc()).offset(offset).limit(limit)
        )
        rows = list((await self._session.execute(page_stmt)).scalars())
        return rows, total

    async def set_latest_version(self, skill: Skill, version_id: int) -> None:
        skill.latest_version_id = version_id
        await self._session.flush()


class SkillVersionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find(self, skill_id: int, version: str) -> SkillVersion | None:
        stmt = (
            select(SkillVersion)
            .where(SkillVersion.skill_id == skill_id)
            .where(SkillVersion.version == version)
            .limit(1)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list_for_skill(
        self, skill_id: int, *, limit: int, offset: int
    ) -> tuple[list[SkillVersion], int]:
        base = select(SkillVersion).where(SkillVersion.skill_id == skill_id)
        total = (
            await self._session.execute(select(func.count()).select_from(base.subquery()))
        ).scalar_one()
        stmt = base.order_by(SkillVersion.created_at.desc()).offset(offset).limit(limit)
        rows = list((await self._session.execute(stmt)).scalars())
        return rows, total

    async def create(
        self,
        *,
        skill_id: int,
        version: str,
        status: str,
        changelog: str | None,
        parsed_metadata: dict | None,
        manifest: dict | None,
        requested_visibility: str | None,
        created_by: str,
    ) -> SkillVersion:
        row = SkillVersion(
            skill_id=skill_id,
            version=version,
            status=status,
            changelog=changelog,
            parsed_metadata_json=parsed_metadata,
            manifest_json=manifest,
            requested_visibility=requested_visibility,
            created_by=created_by,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def mark_published(self, row: SkillVersion, published_at) -> None:
        row.status = "PUBLISHED"
        row.published_at = published_at
        row.download_ready = True
        await self._session.flush()

    async def update_stats(
        self, row: SkillVersion, *, file_count: int, total_size: int, bundle_ready: bool
    ) -> None:
        row.file_count = file_count
        row.total_size = total_size
        row.bundle_ready = bundle_ready
        await self._session.flush()


class SkillFileRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        version_id: int,
        file_path: str,
        file_size: int,
        content_type: str | None,
        sha256: str,
        storage_key: str,
    ) -> SkillFile:
        row = SkillFile(
            version_id=version_id,
            file_path=file_path,
            file_size=file_size,
            content_type=content_type,
            sha256=sha256,
            storage_key=storage_key,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def list_for_version(self, version_id: int) -> list[SkillFile]:
        stmt = (
            select(SkillFile)
            .where(SkillFile.version_id == version_id)
            .order_by(SkillFile.file_path.asc())
        )
        return list((await self._session.execute(stmt)).scalars())
