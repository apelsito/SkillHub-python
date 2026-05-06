"""Skill download service.

Returns either a presigned URL (when the backend supports them, e.g. S3) or
a streamed bytes blob for local/dev mode. Download counters are incremented
here synchronously; Phase 4 will move this to a post-commit event.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from skillhub_api.domain.skill import storage_key_for_bundle
from skillhub_api.errors import ConflictError
from skillhub_api.infra.db.models.skill import Skill, SkillVersion
from skillhub_api.infra.storage.base import ObjectStorage
from skillhub_api.services.skills.query import SkillQueryService


@dataclass(frozen=True, slots=True)
class DownloadResult:
    filename: str
    content_length: int | None
    content_type: str = "application/zip"
    presigned_url: str | None = None
    bytes_: bytes | None = None


class SkillDownloadService:
    def __init__(self, session: AsyncSession, storage: ObjectStorage) -> None:
        self._session = session
        self._storage = storage
        self._query = SkillQueryService(session)

    async def download(
        self,
        *,
        namespace_slug: str,
        slug: str,
        version: str | None,
        presign_expiry: timedelta,
    ) -> DownloadResult:
        if version is None:
            skill = await self._query.get_skill(namespace_slug, slug)
            if skill.latest_version_id is None:
                raise ConflictError("NO_PUBLISHED_VERSION", "skill has no published version")
            version_row = await self._session.get(SkillVersion, skill.latest_version_id)
            if version_row is None:
                raise ConflictError("NO_PUBLISHED_VERSION", "latest version missing")
        else:
            skill, version_row = await self._query.get_version(namespace_slug, slug, version)

        if version_row.status != "PUBLISHED" or not version_row.bundle_ready:
            raise ConflictError("VERSION_NOT_READY", "version not ready for download")

        bundle_key = storage_key_for_bundle(skill.id, version_row.id)
        filename = f"{skill.slug}-{version_row.version}.zip"

        await self._increment_download_count(skill)

        metadata = await self._storage.metadata(bundle_key)
        size = metadata.size if metadata else None
        if hasattr(self._storage, "_session"):
            # Heuristic: S3Storage instances carry an aioboto3 session;
            # LocalFileStorage doesn't. Presign for S3, stream for local.
            url = await self._storage.presigned_url(
                bundle_key, presign_expiry, download_filename=filename
            )
            return DownloadResult(filename=filename, content_length=size, presigned_url=url)
        raw = await self._storage.get_object(bundle_key)
        return DownloadResult(filename=filename, content_length=len(raw), bytes_=raw)

    async def _increment_download_count(self, skill: Skill) -> None:
        from skillhub_api.infra.db.models.skill import Skill as SkillModel

        await self._session.execute(
            update(SkillModel)
            .where(SkillModel.id == skill.id)
            .values(download_count=SkillModel.download_count + 1)
        )
        await self._session.flush()
