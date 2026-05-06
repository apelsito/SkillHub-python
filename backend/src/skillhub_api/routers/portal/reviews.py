"""Review endpoints for both /api/v1 and the browser-facing /api/web API."""

from __future__ import annotations

from datetime import datetime
from pathlib import PurePosixPath
from typing import Any

from fastapi import APIRouter, Depends, Query, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy import asc, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from skillhub_api.deps import Principal, db_session, get_current_principal, require_permission
from skillhub_api.domain.skill import PackageError, storage_key_for_bundle, validate_relative_path
from skillhub_api.errors import NotFoundError
from skillhub_api.events.bus import EventBus, get_event_bus
from skillhub_api.infra.db.models.governance import ReviewTask
from skillhub_api.infra.db.models.namespace import Namespace
from skillhub_api.infra.db.models.skill import Skill, SkillFile, SkillVersion
from skillhub_api.infra.db.models.user import UserAccount
from skillhub_api.infra.storage import ObjectStorage, get_storage
from skillhub_api.schemas.governance import (
    ReviewApproveRequest,
    ReviewListResponse,
    ReviewRejectRequest,
    ReviewSubmitRequest,
    ReviewSummary,
)
from skillhub_api.schemas.skill import SkillLifecycleVersion
from skillhub_api.services.governance.reviews import ReviewService
from skillhub_api.settings import get_settings

router = APIRouter(prefix="/api/v1/reviews", tags=["governance"])
web_router = APIRouter(prefix="/api/web/reviews", tags=["governance"])


def _bus_dep() -> EventBus:
    return get_event_bus()


def storage_dep() -> ObjectStorage:
    return get_storage()


def _summary(row: ReviewTask) -> ReviewSummary:
    return ReviewSummary(
        id=row.id,
        skill_version_id=row.skill_version_id,
        namespace_id=row.namespace_id,
        status=row.status,
        submitted_by=row.submitted_by,
        reviewed_by=row.reviewed_by,
        review_comment=row.review_comment,
        submitted_at=row.submitted_at,
        reviewed_at=row.reviewed_at,
    )


def _page(items: list[dict[str, Any]], total: int, page: int, size: int) -> dict[str, Any]:
    return {"items": items, "total": total, "page": page, "size": size, "limit": size, "offset": page * size}


async def _user_names(db: AsyncSession, user_ids: set[str | None]) -> dict[str, str]:
    clean_ids = {user_id for user_id in user_ids if user_id}
    if not clean_ids:
        return {}
    rows = (
        await db.execute(select(UserAccount.id, UserAccount.display_name).where(UserAccount.id.in_(clean_ids)))
    ).all()
    return {user_id: display_name for user_id, display_name in rows}


async def _review_rows(
    db: AsyncSession,
    *,
    status_filter: str | None,
    namespace_id: int | None,
    submitter_id: str | None,
    page: int,
    size: int,
    sort_direction: str,
) -> tuple[list[tuple[ReviewTask, SkillVersion, Skill, Namespace]], int]:
    base = (
        select(ReviewTask, SkillVersion, Skill, Namespace)
        .join(SkillVersion, SkillVersion.id == ReviewTask.skill_version_id)
        .join(Skill, Skill.id == SkillVersion.skill_id)
        .join(Namespace, Namespace.id == ReviewTask.namespace_id)
    )
    if status_filter:
        base = base.where(ReviewTask.status == status_filter)
    if namespace_id is not None:
        base = base.where(ReviewTask.namespace_id == namespace_id)
    if submitter_id is not None:
        base = base.where(ReviewTask.submitted_by == submitter_id)

    total = int((await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one())
    direction = asc if sort_direction.upper() == "ASC" else desc
    rows = list(
        (
            await db.execute(
                base.order_by(direction(ReviewTask.submitted_at), desc(ReviewTask.id))
                .offset(page * size)
                .limit(size)
            )
        ).all()
    )
    return rows, total


async def _review_dto(
    db: AsyncSession,
    row: ReviewTask,
    version: SkillVersion | None = None,
    skill: Skill | None = None,
    namespace: Namespace | None = None,
    names: dict[str, str] | None = None,
) -> dict[str, Any]:
    if version is None:
        version = await db.get(SkillVersion, row.skill_version_id)
    if version is None:
        raise NotFoundError("VERSION_NOT_FOUND", "review version not found")
    if skill is None:
        skill = await db.get(Skill, version.skill_id)
    if skill is None:
        raise NotFoundError("SKILL_NOT_FOUND", "review skill not found")
    if namespace is None:
        namespace = await db.get(Namespace, row.namespace_id)
    if namespace is None:
        raise NotFoundError("NAMESPACE_NOT_FOUND", "review namespace not found")
    if names is None:
        names = await _user_names(db, {row.submitted_by, row.reviewed_by})
    return {
        "id": row.id,
        "skillVersionId": row.skill_version_id,
        "namespace": namespace.slug,
        "skillSlug": skill.slug,
        "version": version.version,
        "status": row.status,
        "submittedBy": row.submitted_by,
        "submittedByName": names.get(row.submitted_by),
        "reviewedBy": row.reviewed_by,
        "reviewedByName": names.get(row.reviewed_by) if row.reviewed_by else None,
        "reviewComment": row.review_comment,
        "submittedAt": row.submitted_at,
        "reviewedAt": row.reviewed_at,
    }


async def _review_detail_rows(
    db: AsyncSession, review_id: int
) -> tuple[ReviewTask, SkillVersion, Skill, Namespace]:
    row = (
        await db.execute(
            select(ReviewTask, SkillVersion, Skill, Namespace)
            .join(SkillVersion, SkillVersion.id == ReviewTask.skill_version_id)
            .join(Skill, Skill.id == SkillVersion.skill_id)
            .join(Namespace, Namespace.id == ReviewTask.namespace_id)
            .where(ReviewTask.id == review_id)
            .limit(1)
        )
    ).first()
    if row is None:
        raise NotFoundError("REVIEW_NOT_FOUND", f"review {review_id} not found")
    return row


def _version_lifecycle(row: SkillVersion | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return SkillLifecycleVersion(
        id=row.id,
        version=row.version,
        status=row.status,
        published_at=row.published_at,
    ).model_dump(by_alias=True)


def _skill_dto(skill: Skill, namespace: Namespace, version: SkillVersion) -> dict[str, Any]:
    lifecycle = _version_lifecycle(version)
    return {
        "id": skill.id,
        "namespaceId": skill.namespace_id,
        "namespace": namespace.slug,
        "slug": skill.slug,
        "displayName": skill.display_name,
        "summary": skill.summary,
        "ownerId": skill.owner_id,
        "visibility": skill.visibility,
        "status": skill.status,
        "latestVersionId": skill.latest_version_id,
        "downloadCount": skill.download_count,
        "starCount": skill.star_count,
        "ratingAvg": float(skill.rating_avg),
        "ratingCount": skill.rating_count,
        "hidden": skill.hidden,
        "createdAt": skill.created_at,
        "updatedAt": skill.updated_at,
        "canSubmitPromotion": False,
        "canManageLifecycle": False,
        "canInteract": True,
        "canReport": True,
        "headlineVersion": lifecycle,
        "publishedVersion": lifecycle if version.status == "PUBLISHED" else None,
        "ownerPreviewVersion": lifecycle,
        "resolutionMode": "REVIEW",
        "labels": [],
    }


def _version_dto(row: SkillVersion) -> dict[str, Any]:
    return {
        "id": row.id,
        "skillId": row.skill_id,
        "version": row.version,
        "status": row.status,
        "changelog": row.changelog,
        "fileCount": row.file_count,
        "totalSize": row.total_size,
        "publishedAt": row.published_at or row.created_at,
        "downloadAvailable": row.bundle_ready or row.download_ready,
        "bundleReady": row.bundle_ready,
        "downloadReady": row.download_ready,
        "requestedVisibility": row.requested_visibility,
        "createdAt": row.created_at,
        "parsedMetadataJson": row.parsed_metadata_json,
        "manifestJson": row.manifest_json,
    }


def _file_dto(row: SkillFile) -> dict[str, Any]:
    return {
        "id": row.id,
        "filePath": row.file_path,
        "fileSize": row.file_size,
        "contentType": row.content_type,
        "sha256": row.sha256,
    }


async def _review_file(db: AsyncSession, review_id: int, raw_path: str) -> SkillFile:
    try:
        path = validate_relative_path(raw_path)
    except PackageError as exc:
        raise NotFoundError("FILE_NOT_FOUND", "file not found") from exc
    review, version, _skill, _namespace = await _review_detail_rows(db, review_id)
    _ = review
    row = (
        await db.execute(
            select(SkillFile)
            .where(SkillFile.version_id == version.id)
            .where(SkillFile.file_path == path)
            .limit(1)
        )
    ).scalar_one_or_none()
    if row is None:
        raise NotFoundError("FILE_NOT_FOUND", f"file {path!r} not found")
    return row


# ---------- /api/v1 compatibility ----------


@router.get("/pending", response_model=ReviewListResponse)
async def list_pending(
    namespace_id: int | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _principal: Principal = Depends(require_permission("review:approve")),
    db: AsyncSession = Depends(db_session),
    bus: EventBus = Depends(_bus_dep),
) -> ReviewListResponse:
    svc = ReviewService(db, bus)
    rows, total = await svc.list_pending(namespace_id=namespace_id, limit=limit, offset=offset)
    return ReviewListResponse(
        items=[_summary(r) for r in rows], total=total, limit=limit, offset=offset
    )


@router.get("/mine", response_model=ReviewListResponse)
async def list_mine(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(db_session),
    bus: EventBus = Depends(_bus_dep),
) -> ReviewListResponse:
    svc = ReviewService(db, bus)
    rows, total = await svc.list_mine(principal.user_id, limit=limit, offset=offset)
    return ReviewListResponse(
        items=[_summary(r) for r in rows], total=total, limit=limit, offset=offset
    )


@router.post("", response_model=ReviewSummary, status_code=status.HTTP_201_CREATED)
async def submit(
    body: ReviewSubmitRequest,
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(db_session),
    bus: EventBus = Depends(_bus_dep),
) -> ReviewSummary:
    svc = ReviewService(db, bus)
    row = await svc.submit(skill_version_id=body.skill_version_id, submitter_id=principal.user_id)
    await db.commit()
    return _summary(row)


@router.post("/{id}/approve", response_model=ReviewSummary)
async def approve(
    id: int,
    body: ReviewApproveRequest,
    principal: Principal = Depends(require_permission("review:approve")),
    db: AsyncSession = Depends(db_session),
    bus: EventBus = Depends(_bus_dep),
) -> ReviewSummary:
    svc = ReviewService(db, bus)
    row = await svc.approve(review_id=id, reviewer_id=principal.user_id, comment=body.comment)
    await db.commit()
    return _summary(row)


@router.post("/{id}/reject", response_model=ReviewSummary)
async def reject(
    id: int,
    body: ReviewRejectRequest,
    principal: Principal = Depends(require_permission("review:approve")),
    db: AsyncSession = Depends(db_session),
    bus: EventBus = Depends(_bus_dep),
) -> ReviewSummary:
    svc = ReviewService(db, bus)
    row = await svc.reject(review_id=id, reviewer_id=principal.user_id, reason=body.reason)
    await db.commit()
    return _summary(row)


# ---------- /api/web frontend contract ----------


@router.get("")
@web_router.get("")
async def web_list_reviews(
    status_filter: str = Query(default="PENDING", alias="status"),
    namespace_id: int | None = Query(default=None, alias="namespaceId"),
    page: int = Query(default=0, ge=0),
    size: int = Query(default=20, ge=1, le=100),
    sort_direction: str = Query(default="DESC", alias="sortDirection"),
    _principal: Principal = Depends(require_permission("review:approve")),
    db: AsyncSession = Depends(db_session),
) -> dict[str, Any]:
    rows, total = await _review_rows(
        db,
        status_filter=status_filter,
        namespace_id=namespace_id,
        submitter_id=None,
        page=page,
        size=size,
        sort_direction=sort_direction,
    )
    names = await _user_names(db, {r.submitted_by for r, *_ in rows} | {r.reviewed_by for r, *_ in rows})
    return _page(
        [await _review_dto(db, review, version, skill, namespace, names) for review, version, skill, namespace in rows],
        total,
        page,
        size,
    )


@web_router.get("/pending")
async def web_list_pending_reviews(
    namespace_id: int | None = Query(default=None, alias="namespaceId"),
    page: int = Query(default=0, ge=0),
    size: int = Query(default=20, ge=1, le=100),
    _principal: Principal = Depends(require_permission("review:approve")),
    db: AsyncSession = Depends(db_session),
) -> dict[str, Any]:
    return await web_list_reviews("PENDING", namespace_id, page, size, "ASC", _principal, db)


@router.get("/my-submissions")
@web_router.get("/my-submissions")
async def web_my_submissions(
    page: int = Query(default=0, ge=0),
    size: int = Query(default=20, ge=1, le=100),
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(db_session),
) -> dict[str, Any]:
    rows, total = await _review_rows(
        db,
        status_filter=None,
        namespace_id=None,
        submitter_id=principal.user_id,
        page=page,
        size=size,
        sort_direction="DESC",
    )
    names = await _user_names(db, {r.submitted_by for r, *_ in rows} | {r.reviewed_by for r, *_ in rows})
    return _page(
        [await _review_dto(db, review, version, skill, namespace, names) for review, version, skill, namespace in rows],
        total,
        page,
        size,
    )


@web_router.post("", status_code=status.HTTP_201_CREATED)
async def web_submit_review(
    body: ReviewSubmitRequest,
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(db_session),
    bus: EventBus = Depends(_bus_dep),
) -> dict[str, Any]:
    svc = ReviewService(db, bus)
    row = await svc.submit(skill_version_id=body.skill_version_id, submitter_id=principal.user_id)
    await db.commit()
    review, version, skill, namespace = await _review_detail_rows(db, row.id)
    return await _review_dto(db, review, version, skill, namespace)


@router.get("/{id}")
@web_router.get("/{id}")
async def web_get_review(
    id: int,
    _principal: Principal = Depends(require_permission("review:approve")),
    db: AsyncSession = Depends(db_session),
) -> dict[str, Any]:
    review, version, skill, namespace = await _review_detail_rows(db, id)
    return await _review_dto(db, review, version, skill, namespace)


@router.get("/{id}/skill-detail")
@web_router.get("/{id}/skill-detail")
async def web_get_review_skill_detail(
    id: int,
    _principal: Principal = Depends(require_permission("review:approve")),
    db: AsyncSession = Depends(db_session),
    storage: ObjectStorage = Depends(storage_dep),
) -> dict[str, Any]:
    _review, version, skill, namespace = await _review_detail_rows(db, id)
    versions = list(
        (
            await db.execute(
                select(SkillVersion)
                .where(SkillVersion.skill_id == skill.id)
                .order_by(SkillVersion.created_at.desc())
            )
        ).scalars()
    )
    files = list(
        (
            await db.execute(
                select(SkillFile).where(SkillFile.version_id == version.id).order_by(SkillFile.file_path.asc())
            )
        ).scalars()
    )
    documentation_path = next((f.file_path for f in files if PurePosixPath(f.file_path).name.lower() in {"skill.md", "readme.md"}), None)
    documentation_content = None
    if documentation_path:
        doc_file = next(f for f in files if f.file_path == documentation_path)
        try:
            documentation_content = (await storage.get_object(doc_file.storage_key)).decode("utf-8", errors="replace")
        except Exception:
            documentation_content = None
    return {
        "skill": _skill_dto(skill, namespace, version),
        "versions": [_version_dto(v) for v in versions],
        "files": [_file_dto(f) for f in files],
        "documentationPath": documentation_path,
        "documentationContent": documentation_content,
        "downloadUrl": f"/api/web/reviews/{id}/download",
        "activeVersion": version.version,
    }


@router.get("/{id}/file")
@web_router.get("/{id}/file")
async def web_get_review_file(
    id: int,
    path: str = Query(...),
    _principal: Principal = Depends(require_permission("review:approve")),
    db: AsyncSession = Depends(db_session),
    storage: ObjectStorage = Depends(storage_dep),
) -> Response:
    row = await _review_file(db, id, path)
    content = await storage.get_object(row.storage_key)
    return Response(
        content=content,
        media_type=row.content_type or "application/octet-stream",
        headers={"Content-Disposition": f'inline; filename="{PurePosixPath(row.file_path).name}"'},
    )


@router.get("/{id}/download")
@web_router.get("/{id}/download")
async def web_download_review_bundle(
    id: int,
    _principal: Principal = Depends(require_permission("review:approve")),
    db: AsyncSession = Depends(db_session),
    storage: ObjectStorage = Depends(storage_dep),
) -> Response:
    _review, version, skill, _namespace = await _review_detail_rows(db, id)
    key = storage_key_for_bundle(skill.id, version.id)
    filename = f"{skill.slug}-{version.version}.zip"
    metadata = await storage.metadata(key)
    settings = get_settings()
    if metadata and hasattr(storage, "_session"):
        url = await storage.presigned_url(key, settings.storage.s3_presign_expiry, download_filename=filename)
        return RedirectResponse(url=url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
    content = await storage.get_object(key)
    return Response(
        content=content,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@web_router.post("/{id}/approve")
async def web_approve_review(
    id: int,
    body: ReviewApproveRequest,
    principal: Principal = Depends(require_permission("review:approve")),
    db: AsyncSession = Depends(db_session),
    bus: EventBus = Depends(_bus_dep),
) -> dict[str, Any]:
    svc = ReviewService(db, bus)
    row = await svc.approve(review_id=id, reviewer_id=principal.user_id, comment=body.comment)
    await db.commit()
    review, version, skill, namespace = await _review_detail_rows(db, row.id)
    return await _review_dto(db, review, version, skill, namespace)


@web_router.post("/{id}/reject")
async def web_reject_review(
    id: int,
    body: ReviewApproveRequest,
    principal: Principal = Depends(require_permission("review:approve")),
    db: AsyncSession = Depends(db_session),
    bus: EventBus = Depends(_bus_dep),
) -> dict[str, Any]:
    svc = ReviewService(db, bus)
    comment = body.comment or ""
    if not comment.strip():
        from skillhub_api.errors import ConflictError

        raise ConflictError("REVIEW_REJECT_REASON_REQUIRED", "reject comment is required")
    row = await svc.reject(review_id=id, reviewer_id=principal.user_id, reason=comment)
    await db.commit()
    review, version, skill, namespace = await _review_detail_rows(db, row.id)
    return await _review_dto(db, review, version, skill, namespace)


@router.post("/{id}/withdraw")
@web_router.post("/{id}/withdraw")
async def web_withdraw_review(
    id: int,
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(db_session),
) -> dict[str, Any]:
    review, version, skill, namespace = await _review_detail_rows(db, id)
    if review.submitted_by != principal.user_id:
        from skillhub_api.errors import ForbiddenError

        raise ForbiddenError("NOT_REVIEW_SUBMITTER", "only the submitter can withdraw this review")
    if review.status != "PENDING":
        from skillhub_api.errors import ConflictError

        raise ConflictError("REVIEW_NOT_PENDING", f"review already {review.status}")
    review.status = "WITHDRAWN"
    version.status = "DRAFT"
    await db.commit()
    return await _review_dto(db, review, version, skill, namespace)
