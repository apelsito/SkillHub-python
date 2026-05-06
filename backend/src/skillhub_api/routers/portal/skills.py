"""Skill portal routes — /api/web/skills/... and /api/v1/skills/...

Contract-compatible with the Java ``SkillController`` + ``SkillPublishController``
+ ``SkillLifecycleController``. For the Python port, we mount the same paths
under ``/api/v1/skills`` (the source of truth for the generated types).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import RedirectResponse
from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from skillhub_api.deps import Principal, db_session, get_current_principal
from skillhub_api.domain.skill import Visibility
from skillhub_api.errors import DomainError
from skillhub_api.infra.db.models.label import LabelDefinition, SkillLabel
from skillhub_api.infra.db.models.namespace import Namespace
from skillhub_api.events.bus import get_event_bus
from skillhub_api.infra.db.models.governance import PromotionRequest, ReviewTask, SkillReport
from skillhub_api.infra.db.models.search import SkillSearchDocument
from skillhub_api.infra.db.models.skill import (
    Skill,
    SkillFile,
    SkillTag,
    SkillVersion,
    SkillVersionStats,
)
from skillhub_api.infra.db.models.social import SkillRating, SkillStar, SkillSubscription
from skillhub_api.infra.storage import ObjectStorage, get_storage
from skillhub_api.schemas.skill import (
    DownloadResponse,
    LifecycleResponse,
    PublishResponse,
    SkillDetailResponse,
    SkillFileResponse,
    SkillListResponse,
    SkillSummary,
    SkillVersionDetailResponse,
    SkillVersionListResponse,
    SkillVersionSummary,
    VersionYankedResponse,
    YankRequest,
)
from skillhub_api.schemas.base import ApiModel
from skillhub_api.services.governance.reviews import ReviewService
from skillhub_api.services.skills.download import SkillDownloadService
from skillhub_api.services.skills.lifecycle import SkillLifecycleService
from skillhub_api.services.skills.package import PackageError
from skillhub_api.services.skills.publish import SkillPublishService
from skillhub_api.services.skills.query import SkillQueryService
from skillhub_api.settings import get_settings

router = APIRouter(prefix="/api/v1/skills", tags=["skills"])
web_router = APIRouter(prefix="/api/web/skills", tags=["skills"])


class SkillLifecycleMutationResponse(ApiModel):
    skill_id: int
    version_id: int | None = None
    action: str
    status: str


class SubmitReviewRequest(ApiModel):
    version: str
    target_visibility: str


class ConfirmPublishRequest(ApiModel):
    version: str


class SkillVersionRereleaseRequest(ApiModel):
    target_version: str
    confirm_warnings: bool = False


class ResolveVersionResponse(ApiModel):
    skill_id: int
    version_id: int
    version: str
    status: str


def storage_dep() -> ObjectStorage:
    return get_storage()


def _version_lifecycle(row: SkillVersion | None):
    if row is None:
        return None
    from skillhub_api.schemas.skill import SkillLifecycleVersion

    return SkillLifecycleVersion(id=row.id, version=row.version, status=row.status, published_at=row.published_at)


def _skill_summary(row: Skill, namespace_slug: str | None = None) -> SkillSummary:
    return SkillSummary(
        id=row.id,
        namespace_id=row.namespace_id,
        namespace=namespace_slug,
        slug=row.slug,
        display_name=row.display_name,
        summary=row.summary,
        owner_id=row.owner_id,
        visibility=row.visibility,
        status=row.status,
        latest_version_id=row.latest_version_id,
        download_count=row.download_count,
        star_count=row.star_count,
        rating_avg=Decimal(row.rating_avg),
        rating_count=row.rating_count,
        hidden=row.hidden,
        created_at=row.created_at,
        updated_at=row.updated_at,
        can_submit_promotion=False,
        can_manage_lifecycle=False,
        can_interact=True,
        can_report=True,
    )


def _version_summary(row: SkillVersion) -> SkillVersionSummary:
    return SkillVersionSummary(
        id=row.id,
        skill_id=row.skill_id,
        version=row.version,
        status=row.status,
        file_count=row.file_count,
        total_size=row.total_size,
        bundle_ready=row.bundle_ready,
        download_ready=row.download_ready,
        requested_visibility=row.requested_visibility,
        published_at=row.published_at,
        created_at=row.created_at,
    )


def _file_response(row: SkillFile) -> SkillFileResponse:
    return SkillFileResponse(
        file_path=row.file_path,
        file_size=row.file_size,
        content_type=row.content_type,
        sha256=row.sha256,
    )


async def _namespace_slugs(db: AsyncSession, namespace_ids: set[int]) -> dict[int, str]:
    if not namespace_ids:
        return {}
    rows = (
        await db.execute(select(Namespace.id, Namespace.slug).where(Namespace.id.in_(namespace_ids)))
    ).all()
    return {namespace_id: slug for namespace_id, slug in rows}


def _page_response(items: list[SkillSummary], total: int, page: int, size: int) -> SkillListResponse:
    return SkillListResponse(
        items=items,
        total=total,
        limit=size,
        offset=page * size,
        page=page,
        size=size,
    )


def _translate_package_error(exc: PackageError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


# ---------- listing ----------


@router.get("", response_model=SkillListResponse)
async def list_skills(
    namespace: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(db_session),
) -> SkillListResponse:
    svc = SkillQueryService(db)
    page = await svc.list_skills(namespace_slug=namespace, limit=limit, offset=offset)
    ns_by_id = await _namespace_slugs(db, {s.namespace_id for s in page.items})
    return SkillListResponse(
        items=[_skill_summary(s, ns_by_id.get(s.namespace_id)) for s in page.items],
        total=page.total,
        limit=page.limit,
        offset=page.offset,
        page=page.offset // page.limit if page.limit else 0,
        size=page.limit,
    )


@web_router.get("", response_model=SkillListResponse)
async def web_list_skills(
    q: str | None = Query(default=None),
    namespace: str | None = Query(default=None),
    label: str | None = Query(default=None),
    sort: str = Query(default="newest"),
    page: int = Query(default=0, ge=0),
    size: int = Query(default=12, ge=1, le=100),
    db: AsyncSession = Depends(db_session),
) -> SkillListResponse:
    stmt = (
        select(Skill, Namespace.slug)
        .join(Namespace, Namespace.id == Skill.namespace_id)
        .where(Skill.status == "ACTIVE")
        .where(Skill.hidden.is_(False))
    )
    count_stmt = (
        select(func.count())
        .select_from(Skill)
        .join(Namespace, Namespace.id == Skill.namespace_id)
        .where(Skill.status == "ACTIVE")
        .where(Skill.hidden.is_(False))
    )
    if namespace:
        clean_namespace = namespace[1:] if namespace.startswith("@") else namespace
        stmt = stmt.where(Namespace.slug == clean_namespace)
        count_stmt = count_stmt.where(Namespace.slug == clean_namespace)
    if q and q.strip():
        pattern = f"%{q.strip()}%"
        predicate = or_(
            Skill.slug.ilike(pattern),
            Skill.display_name.ilike(pattern),
            Skill.summary.ilike(pattern),
        )
        stmt = stmt.where(predicate)
        count_stmt = count_stmt.where(predicate)
    if label:
        stmt = (
            stmt.join(SkillLabel, SkillLabel.skill_id == Skill.id)
            .join(LabelDefinition, LabelDefinition.id == SkillLabel.label_id)
            .where(LabelDefinition.slug == label)
        )
        count_stmt = (
            count_stmt.join(SkillLabel, SkillLabel.skill_id == Skill.id)
            .join(LabelDefinition, LabelDefinition.id == SkillLabel.label_id)
            .where(LabelDefinition.slug == label)
        )

    order = {
        "downloads": (Skill.download_count.desc(), Skill.updated_at.desc(), Skill.id.desc()),
        "rating": (Skill.rating_avg.desc(), Skill.rating_count.desc(), Skill.updated_at.desc()),
        "newest": (Skill.updated_at.desc(), Skill.id.desc()),
        "relevance": (Skill.updated_at.desc(), Skill.id.desc()),
    }.get(sort, (Skill.updated_at.desc(), Skill.id.desc()))
    total = int((await db.execute(count_stmt)).scalar_one())
    rows = list(
        (await db.execute(stmt.order_by(*order).offset(page * size).limit(size))).all()
    )
    return _page_response(
        [_skill_summary(skill, namespace_slug) for skill, namespace_slug in rows],
        total,
        page,
        size,
    )


@router.get("/{namespace}/{slug}", response_model=SkillDetailResponse)
async def get_skill(
    namespace: str, slug: str, db: AsyncSession = Depends(db_session)
) -> SkillDetailResponse:
    svc = SkillQueryService(db)
    row = await svc.get_skill(namespace, slug)
    return SkillDetailResponse(**_skill_summary(row, namespace).model_dump(), labels=[])


@router.get("/{namespace}/{slug}/versions", response_model=SkillVersionListResponse)
async def list_versions(
    namespace: str,
    slug: str,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(db_session),
) -> SkillVersionListResponse:
    svc = SkillQueryService(db)
    page = await svc.list_versions(namespace, slug, limit=limit, offset=offset)
    return SkillVersionListResponse(
        items=[_version_summary(v) for v in page.items],
        total=page.total,
        limit=page.limit,
        offset=page.offset,
        page=page.offset // page.limit if page.limit else 0,
        size=page.limit,
    )


@router.get("/{namespace}/{slug}/versions/{version}", response_model=SkillVersionDetailResponse)
async def get_version(
    namespace: str,
    slug: str,
    version: str,
    db: AsyncSession = Depends(db_session),
) -> SkillVersionDetailResponse:
    svc = SkillQueryService(db)
    _, row = await svc.get_version(namespace, slug, version)
    summary = _version_summary(row)
    return SkillVersionDetailResponse(
        **summary.model_dump(),
        parsed_metadata_json=row.parsed_metadata_json,
        manifest_json=row.manifest_json,
        changelog=row.changelog,
        yanked_at=row.yanked_at,
        yank_reason=row.yank_reason,
    )


@router.get(
    "/{namespace}/{slug}/versions/{version}/files",
    response_model=list[SkillFileResponse],
)
async def list_files(
    namespace: str,
    slug: str,
    version: str,
    db: AsyncSession = Depends(db_session),
) -> list[SkillFileResponse]:
    svc = SkillQueryService(db)
    rows = await svc.list_files(namespace, slug, version)
    return [_file_response(r) for r in rows]


@router.get("/{namespace}/{slug}/versions/{version}/file")
async def get_file_content(
    namespace: str,
    slug: str,
    version: str,
    path: str = Query(...),
    db: AsyncSession = Depends(db_session),
    storage: ObjectStorage = Depends(storage_dep),
) -> Response:
    svc = SkillQueryService(db)
    _, version_row = await svc.get_version(namespace, slug, version)
    row = (
        await db.execute(
            select(SkillFile)
            .where(SkillFile.version_id == version_row.id)
            .where(SkillFile.file_path == path)
            .limit(1)
        )
    ).scalar_one_or_none()
    if row is None:
        from skillhub_api.errors import NotFoundError

        raise NotFoundError("FILE_NOT_FOUND", f"file {path!r} not found")
    content = await storage.get_object(row.storage_key)
    return Response(content=content, media_type=row.content_type or "text/plain")


async def _version_for_tag(
    db: AsyncSession,
    namespace: str,
    slug: str,
    tag_name: str,
) -> tuple[Skill, SkillVersion]:
    svc = SkillQueryService(db)
    skill = await svc.get_skill(namespace, slug)
    tag = (
        await db.execute(
            select(SkillTag)
            .where(SkillTag.skill_id == skill.id)
            .where(SkillTag.tag_name == tag_name)
            .limit(1)
        )
    ).scalar_one_or_none()
    if tag is None:
        from skillhub_api.errors import NotFoundError

        raise NotFoundError("TAG_NOT_FOUND", f"tag {tag_name!r} not found")
    version = await db.get(SkillVersion, tag.version_id)
    if version is None:
        from skillhub_api.errors import NotFoundError

        raise NotFoundError("VERSION_NOT_FOUND", "tag target version not found")
    return skill, version


@router.get("/{namespace}/{slug}/tags/{tagName}/files", response_model=list[SkillFileResponse])
async def list_files_by_tag(
    namespace: str,
    slug: str,
    tagName: str,
    db: AsyncSession = Depends(db_session),
) -> list[SkillFileResponse]:
    _skill, version = await _version_for_tag(db, namespace, slug, tagName)
    rows = list(
        (
            await db.execute(
                select(SkillFile)
                .where(SkillFile.version_id == version.id)
                .order_by(SkillFile.file_path.asc())
            )
        ).scalars()
    )
    return [_file_response(r) for r in rows]


@router.get("/{namespace}/{slug}/tags/{tagName}/file")
async def get_file_content_by_tag(
    namespace: str,
    slug: str,
    tagName: str,
    path: str = Query(...),
    db: AsyncSession = Depends(db_session),
    storage: ObjectStorage = Depends(storage_dep),
) -> Response:
    _skill, version = await _version_for_tag(db, namespace, slug, tagName)
    row = (
        await db.execute(
            select(SkillFile)
            .where(SkillFile.version_id == version.id)
            .where(SkillFile.file_path == path)
            .limit(1)
        )
    ).scalar_one_or_none()
    if row is None:
        from skillhub_api.errors import NotFoundError

        raise NotFoundError("FILE_NOT_FOUND", f"file {path!r} not found")
    content = await storage.get_object(row.storage_key)
    return Response(content=content, media_type=row.content_type or "text/plain")


@router.get("/{namespace}/{slug}/resolve", response_model=ResolveVersionResponse)
async def resolve_version(
    namespace: str,
    slug: str,
    version: str | None = Query(default=None),
    tag: str | None = Query(default=None),
    db: AsyncSession = Depends(db_session),
) -> ResolveVersionResponse:
    svc = SkillQueryService(db)
    skill = await svc.get_skill(namespace, slug)
    if tag:
        _, row = await _version_for_tag(db, namespace, slug, tag)
    elif version and version != "latest":
        _, row = await svc.get_version(namespace, slug, version)
    else:
        if skill.latest_version_id is None:
            from skillhub_api.errors import NotFoundError

            raise NotFoundError("VERSION_NOT_FOUND", "latest version not found")
        row = await db.get(SkillVersion, skill.latest_version_id)
        if row is None:
            from skillhub_api.errors import NotFoundError

            raise NotFoundError("VERSION_NOT_FOUND", "latest version not found")
    return ResolveVersionResponse(
        skill_id=skill.id,
        version_id=row.id,
        version=row.version,
        status=row.status,
    )


# ---------- publish ----------


@router.post(
    "/{namespace}/publish",
    response_model=PublishResponse,
    status_code=status.HTTP_201_CREATED,
)
async def publish(
    namespace: str,
    file: UploadFile = File(...),
    visibility: Visibility = Form(default=Visibility.PRIVATE),
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(db_session),
    storage: ObjectStorage = Depends(storage_dep),
) -> PublishResponse:
    svc = SkillPublishService(db, storage)
    zip_bytes = await file.read()
    try:
        result = await svc.publish(
            namespace_slug=namespace,
            zip_bytes=zip_bytes,
            visibility=visibility,
            owner_id=principal.user_id,
        )
    except PackageError as exc:
        await db.rollback()
        raise DomainError(exc.code, str(exc)) from exc
    await db.commit()
    return PublishResponse(
        skill_id=result.skill.id,
        namespace_id=result.skill.namespace_id,
        slug=result.skill.slug,
        version=result.version.version,
        status=result.version.status,
        visibility=result.skill.visibility,
        file_count=result.version.file_count,
        total_size=result.version.total_size,
    )


# ---------- download ----------


async def _download_internal(
    namespace: str, slug: str, version: str | None, db: AsyncSession, storage: ObjectStorage
):
    svc = SkillDownloadService(db, storage)
    settings = get_settings()
    result = await svc.download(
        namespace_slug=namespace,
        slug=slug,
        version=version,
        presign_expiry=settings.storage.s3_presign_expiry,
    )
    await db.commit()
    return result


@router.get("/{namespace}/{slug}/download")
async def download_latest(
    namespace: str,
    slug: str,
    db: AsyncSession = Depends(db_session),
    storage: ObjectStorage = Depends(storage_dep),
) -> Response:
    result = await _download_internal(namespace, slug, None, db, storage)
    if result.presigned_url is not None:
        return RedirectResponse(
            url=result.presigned_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT
        )
    return Response(
        content=result.bytes_ or b"",
        media_type=result.content_type,
        headers={"Content-Disposition": f'attachment; filename="{result.filename}"'},
    )


@router.get("/{namespace}/{slug}/versions/{version}/download")
async def download_version(
    namespace: str,
    slug: str,
    version: str,
    db: AsyncSession = Depends(db_session),
    storage: ObjectStorage = Depends(storage_dep),
) -> Response:
    result = await _download_internal(namespace, slug, version, db, storage)
    if result.presigned_url is not None:
        return RedirectResponse(
            url=result.presigned_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT
        )
    return Response(
        content=result.bytes_ or b"",
        media_type=result.content_type,
        headers={"Content-Disposition": f'attachment; filename="{result.filename}"'},
    )


@router.get("/{namespace}/{slug}/tags/{tagName}/download")
async def download_tag(
    namespace: str,
    slug: str,
    tagName: str,
    db: AsyncSession = Depends(db_session),
    storage: ObjectStorage = Depends(storage_dep),
) -> Response:
    _skill, version = await _version_for_tag(db, namespace, slug, tagName)
    return await download_version(namespace, slug, version.version, db, storage)


@router.get(
    "/{namespace}/{slug}/download/info",
    response_model=DownloadResponse,
)
async def download_info(
    namespace: str,
    slug: str,
    db: AsyncSession = Depends(db_session),
    storage: ObjectStorage = Depends(storage_dep),
) -> DownloadResponse:
    result = await _download_internal(namespace, slug, None, db, storage)
    return DownloadResponse(
        filename=result.filename,
        content_length=result.content_length,
        content_type=result.content_type,
        presigned_url=result.presigned_url,
    )


# ---------- lifecycle ----------


@router.post("/{namespace}/{slug}/archive", response_model=LifecycleResponse)
async def archive(
    namespace: str,
    slug: str,
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(db_session),
) -> LifecycleResponse:
    svc = SkillLifecycleService(db)
    row = await svc.archive(namespace_slug=namespace, slug=slug, actor_id=principal.user_id)
    await db.commit()
    return LifecycleResponse(skill_id=row.id, slug=row.slug, status=row.status, hidden=row.hidden)


@router.post("/{namespace}/{slug}/unarchive", response_model=LifecycleResponse)
async def unarchive(
    namespace: str,
    slug: str,
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(db_session),
) -> LifecycleResponse:
    svc = SkillLifecycleService(db)
    row = await svc.unarchive(namespace_slug=namespace, slug=slug, actor_id=principal.user_id)
    await db.commit()
    return LifecycleResponse(skill_id=row.id, slug=row.slug, status=row.status, hidden=row.hidden)


async def _delete_skill_row(
    db: AsyncSession,
    skill: Skill,
    principal: Principal,
    namespace_slug: str,
) -> dict:
    if skill.owner_id != principal.user_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "only the skill owner can delete this skill")
    version_ids = list(
        (
            await db.execute(select(SkillVersion.id).where(SkillVersion.skill_id == skill.id))
        ).scalars()
    )
    skill.latest_version_id = None
    await db.flush()
    await db.execute(delete(SkillSearchDocument).where(SkillSearchDocument.skill_id == skill.id))
    await db.execute(delete(SkillVersionStats).where(SkillVersionStats.skill_id == skill.id))
    if version_ids:
        await db.execute(delete(SkillFile).where(SkillFile.version_id.in_(version_ids)))
        await db.execute(delete(SkillTag).where(SkillTag.version_id.in_(version_ids)))
        await db.execute(delete(ReviewTask).where(ReviewTask.skill_version_id.in_(version_ids)))
        await db.execute(delete(SkillVersion).where(SkillVersion.id.in_(version_ids)))
    await db.execute(delete(SkillLabel).where(SkillLabel.skill_id == skill.id))
    await db.execute(delete(SkillStar).where(SkillStar.skill_id == skill.id))
    await db.execute(delete(SkillRating).where(SkillRating.skill_id == skill.id))
    await db.execute(delete(SkillSubscription).where(SkillSubscription.skill_id == skill.id))
    await db.execute(delete(SkillReport).where(SkillReport.skill_id == skill.id))
    await db.execute(
        delete(PromotionRequest).where(
            or_(
                PromotionRequest.source_skill_id == skill.id,
                PromotionRequest.target_skill_id == skill.id,
            )
        )
    )
    await db.delete(skill)
    await db.commit()
    return {
        "skillId": skill.id,
        "namespace": namespace_slug,
        "slug": skill.slug,
        "deleted": True,
    }


@router.delete("/id/{skillId}")
async def delete_skill_by_id(
    skillId: int,
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(db_session),
) -> dict:
    skill = await db.get(Skill, skillId)
    if skill is None:
        from skillhub_api.errors import NotFoundError

        raise NotFoundError("SKILL_NOT_FOUND", "skill not found")
    namespace = await db.get(Namespace, skill.namespace_id)
    return await _delete_skill_row(db, skill, principal, namespace.slug if namespace else "")


@router.delete("/{namespace}/{slug}")
async def delete_skill(
    namespace: str,
    slug: str,
    owner_id: str | None = Query(default=None, alias="ownerId"),
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(db_session),
) -> dict:
    ns = (
        await db.execute(select(Namespace).where(Namespace.slug == namespace).limit(1))
    ).scalar_one_or_none()
    if ns is None:
        from skillhub_api.errors import NotFoundError

        raise NotFoundError("NAMESPACE_NOT_FOUND", f"namespace {namespace!r} not found")
    effective_owner = owner_id or principal.user_id
    skill = (
        await db.execute(
            select(Skill)
            .where(Skill.namespace_id == ns.id)
            .where(Skill.slug == slug)
            .where(Skill.owner_id == effective_owner)
            .limit(1)
        )
    ).scalar_one_or_none()
    if skill is None:
        from skillhub_api.errors import NotFoundError

        raise NotFoundError("SKILL_NOT_FOUND", f"{namespace}/{slug} not found")
    return await _delete_skill_row(db, skill, principal, ns.slug)


@router.post(
    "/{namespace}/{slug}/versions/{version}/yank",
    response_model=VersionYankedResponse,
)
async def yank_version(
    namespace: str,
    slug: str,
    version: str,
    body: YankRequest,
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(db_session),
) -> VersionYankedResponse:
    svc = SkillLifecycleService(db)
    row = await svc.yank_version(
        namespace_slug=namespace,
        slug=slug,
        version=version,
        reason=body.reason,
        actor_id=principal.user_id,
    )
    await db.commit()
    return VersionYankedResponse(
        skill_id=row.skill_id,
        version_id=row.id,
        version=row.version,
        status=row.status,
    )


async def _owned_version(
    db: AsyncSession,
    namespace: str,
    slug: str,
    version: str,
    principal: Principal,
) -> tuple[Skill, SkillVersion]:
    svc = SkillQueryService(db)
    skill, row = await svc.get_version(namespace, slug, version)
    if skill.owner_id != principal.user_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "only the skill owner can mutate versions")
    return skill, row


@router.delete(
    "/{namespace}/{slug}/versions/{version}",
    response_model=SkillLifecycleMutationResponse,
)
async def delete_version(
    namespace: str,
    slug: str,
    version: str,
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(db_session),
) -> SkillLifecycleMutationResponse:
    skill, row = await _owned_version(db, namespace, slug, version, principal)
    await db.execute(delete(SkillFile).where(SkillFile.version_id == row.id))
    await db.execute(delete(SkillTag).where(SkillTag.version_id == row.id))
    await db.execute(delete(ReviewTask).where(ReviewTask.skill_version_id == row.id))
    await db.execute(delete(SkillVersionStats).where(SkillVersionStats.skill_version_id == row.id))
    if skill.latest_version_id == row.id:
        skill.latest_version_id = None
    await db.delete(row)
    await db.commit()
    return SkillLifecycleMutationResponse(
        skill_id=skill.id,
        version_id=row.id,
        action="DELETE_VERSION",
        status="DELETED",
    )


@router.post(
    "/{namespace}/{slug}/versions/{version}/withdraw-review",
    response_model=SkillLifecycleMutationResponse,
)
async def withdraw_review(
    namespace: str,
    slug: str,
    version: str,
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(db_session),
) -> SkillLifecycleMutationResponse:
    skill, row = await _owned_version(db, namespace, slug, version, principal)
    review = (
        await db.execute(
            select(ReviewTask)
            .where(ReviewTask.skill_version_id == row.id)
            .where(ReviewTask.status == "PENDING")
            .limit(1)
        )
    ).scalar_one_or_none()
    if review is not None:
        review.status = "WITHDRAWN"
        review.reviewed_at = datetime.now(UTC)
    row.status = "DRAFT"
    await db.commit()
    return SkillLifecycleMutationResponse(
        skill_id=skill.id,
        version_id=row.id,
        action="WITHDRAW_REVIEW",
        status=row.status,
    )


@router.post(
    "/{namespace}/{slug}/submit-review",
    response_model=SkillLifecycleMutationResponse,
)
async def submit_review(
    namespace: str,
    slug: str,
    body: SubmitReviewRequest,
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(db_session),
) -> SkillLifecycleMutationResponse:
    skill, row = await _owned_version(db, namespace, slug, body.version, principal)
    target_visibility = body.target_visibility.upper()
    if target_visibility not in {"PUBLIC", "NAMESPACE_ONLY"}:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "targetVisibility must be PUBLIC or NAMESPACE_ONLY")
    row.requested_visibility = target_visibility
    review = await ReviewService(db, get_event_bus()).submit(
        skill_version_id=row.id,
        submitter_id=principal.user_id,
    )
    _ = review
    await db.commit()
    return SkillLifecycleMutationResponse(
        skill_id=skill.id,
        version_id=row.id,
        action="SUBMIT_REVIEW",
        status=row.status,
    )


@router.post(
    "/{namespace}/{slug}/confirm-publish",
    response_model=SkillLifecycleMutationResponse,
)
async def confirm_publish(
    namespace: str,
    slug: str,
    body: ConfirmPublishRequest,
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(db_session),
) -> SkillLifecycleMutationResponse:
    skill, row = await _owned_version(db, namespace, slug, body.version, principal)
    if row.status == "PUBLISHED":
        return SkillLifecycleMutationResponse(
            skill_id=skill.id,
            version_id=row.id,
            action="CONFIRM_PUBLISH",
            status=row.status,
        )
    now = datetime.now(UTC)
    row.status = "PUBLISHED"
    row.published_at = now
    row.download_ready = True
    skill.latest_version_id = row.id
    skill.visibility = "PRIVATE"
    await db.commit()
    return SkillLifecycleMutationResponse(
        skill_id=skill.id,
        version_id=row.id,
        action="CONFIRM_PUBLISH",
        status=row.status,
    )


@router.post(
    "/{namespace}/{slug}/versions/{version}/rerelease",
    response_model=SkillLifecycleMutationResponse,
)
async def rerelease_version(
    namespace: str,
    slug: str,
    version: str,
    body: SkillVersionRereleaseRequest,
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(db_session),
) -> SkillLifecycleMutationResponse:
    skill, source = await _owned_version(db, namespace, slug, version, principal)
    existing = (
        await db.execute(
            select(SkillVersion)
            .where(SkillVersion.skill_id == skill.id)
            .where(SkillVersion.version == body.target_version)
            .limit(1)
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "target version already exists")
    now = datetime.now(UTC)
    row = SkillVersion(
        skill_id=skill.id,
        version=body.target_version,
        status="PUBLISHED",
        changelog=source.changelog,
        parsed_metadata_json=source.parsed_metadata_json,
        manifest_json=source.manifest_json,
        file_count=source.file_count,
        total_size=source.total_size,
        bundle_ready=source.bundle_ready,
        download_ready=source.download_ready,
        requested_visibility=source.requested_visibility or skill.visibility,
        published_at=now,
        created_by=principal.user_id,
    )
    db.add(row)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "target version already exists") from exc
    for source_file in (
        await db.execute(
            select(SkillFile)
            .where(SkillFile.version_id == source.id)
            .order_by(SkillFile.file_path.asc())
        )
    ).scalars():
        db.add(
            SkillFile(
                version_id=row.id,
                file_path=source_file.file_path,
                file_size=source_file.file_size,
                content_type=source_file.content_type,
                sha256=source_file.sha256,
                storage_key=source_file.storage_key,
            )
        )
    skill.latest_version_id = row.id
    await db.commit()
    return SkillLifecycleMutationResponse(
        skill_id=skill.id,
        version_id=row.id,
        action="RERELEASE_VERSION",
        status=row.status,
    )
