"""Skill publish service.

Thinned port of ``SkillPublishService.java`` — same contract (multipart
upload, SKILL.md frontmatter, storage layout, version table row) but
without the scanner integration and review-task creation. Those land in
Phases 4 and 7 respectively; until then, PUBLIC/NAMESPACE_ONLY uploads
land in ``PENDING_REVIEW`` status so the UI shows them correctly.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from skillhub_api.domain.events import SkillPublishedEvent
from skillhub_api.domain.skill import (
    SkillVersionStatus,
    Visibility,
    storage_key_for_bundle,
    storage_key_for_file,
)
from skillhub_api.errors import ConflictError, NotFoundError
from skillhub_api.events.bus import get_event_bus
from skillhub_api.infra.db.models.skill import Skill, SkillVersion
from skillhub_api.infra.repositories.skill import (
    NamespaceRepository,
    SkillFileRepository,
    SkillRepository,
    SkillVersionRepository,
)
from skillhub_api.infra.storage.base import ObjectStorage
from skillhub_api.services.skills.bundle import build_bundle
from skillhub_api.services.skills.manifest import parse_manifest
from skillhub_api.services.skills.package import ExtractedPackage, extract_package, slugify


@dataclass(frozen=True, slots=True)
class PublishResult:
    skill: Skill
    version: SkillVersion


def _auto_version() -> str:
    # Matches Java `yyyyMMdd.HHmmss` auto-generated version.
    now = datetime.now(UTC)
    return now.strftime("%Y%m%d.%H%M%S")


def _initial_status(visibility: Visibility) -> SkillVersionStatus:
    if visibility == Visibility.PRIVATE:
        return SkillVersionStatus.PUBLISHED
    return SkillVersionStatus.PENDING_REVIEW


class SkillPublishService:
    def __init__(self, session: AsyncSession, storage: ObjectStorage) -> None:
        self._session = session
        self._storage = storage
        self._namespaces = NamespaceRepository(session)
        self._skills = SkillRepository(session)
        self._versions = SkillVersionRepository(session)
        self._files = SkillFileRepository(session)

    async def publish(
        self,
        *,
        namespace_slug: str,
        zip_bytes: bytes,
        visibility: Visibility,
        owner_id: str,
    ) -> PublishResult:
        ns = await self._namespaces.find_by_slug(namespace_slug)
        if ns is None:
            raise NotFoundError("NAMESPACE_NOT_FOUND", f"namespace {namespace_slug!r} not found")

        package = extract_package(zip_bytes)
        manifest = parse_manifest(package.manifest_source)
        slug = slugify(manifest.name)
        version = manifest.version or _auto_version()

        skill = await self._skills.find_owned(ns.id, slug, owner_id)
        if skill is None:
            skill = await self._skills.create(
                namespace_id=ns.id,
                slug=slug,
                display_name=manifest.name,
                summary=manifest.description,
                owner_id=owner_id,
                visibility=visibility.value,
                created_by=owner_id,
            )
        else:
            skill.visibility = visibility.value
            skill.display_name = manifest.name
            skill.summary = manifest.description
            skill.updated_by = owner_id

        existing_version = await self._versions.find(skill.id, version)
        if (
            existing_version is not None
            and existing_version.status == SkillVersionStatus.PUBLISHED.value
        ):
            raise ConflictError(
                "VERSION_EXISTS",
                f"version {version!r} already published",
            )

        row = await self._versions.create(
            skill_id=skill.id,
            version=version,
            status=_initial_status(visibility).value,
            changelog=None,
            parsed_metadata={"name": manifest.name, "description": manifest.description},
            manifest=manifest.frontmatter,
            requested_visibility=visibility.value,
            created_by=owner_id,
        )

        await self._upload_files(skill.id, row.id, package)

        bundle_key = storage_key_for_bundle(skill.id, row.id)
        bundle_bytes = build_bundle(package.files)
        await self._storage.put_object(bundle_key, bundle_bytes, content_type="application/zip")

        await self._versions.update_stats(
            row,
            file_count=package.file_count,
            total_size=package.total_size,
            bundle_ready=True,
        )
        if visibility == Visibility.PRIVATE:
            now = datetime.now(UTC)
            await self._versions.mark_published(row, now)
            await self._skills.set_latest_version(skill, row.id)
            get_event_bus().enqueue(
                SkillPublishedEvent(
                    occurred_at=now,
                    skill_id=skill.id,
                    version_id=row.id,
                    publisher_id=owner_id,
                )
            )

        return PublishResult(skill=skill, version=row)

    async def _upload_files(
        self,
        skill_id: int,
        version_id: int,
        package: ExtractedPackage,
    ) -> None:
        for f in package.files:
            key = storage_key_for_file(skill_id, version_id, f.path)
            await self._storage.put_object(key, f.data, content_type=_guess_content_type(f.path))
            await self._files.create(
                version_id=version_id,
                file_path=f.path,
                file_size=len(f.data),
                content_type=_guess_content_type(f.path),
                sha256=f.sha256,
                storage_key=key,
            )


def _guess_content_type(path: str) -> str | None:
    # Keep this small and explicit — mimetypes has different answers per
    # platform, which would leak into the DB. Unknown → NULL.
    mapping = {
        ".md": "text/markdown",
        ".txt": "text/plain",
        ".json": "application/json",
        ".yaml": "application/yaml",
        ".yml": "application/yaml",
        ".html": "text/html",
        ".css": "text/css",
        ".csv": "text/csv",
        ".pdf": "application/pdf",
        ".xml": "application/xml",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".svg": "image/svg+xml",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }
    dot = path.rfind(".")
    if dot < 0:
        return None
    return mapping.get(path[dot:].lower())
