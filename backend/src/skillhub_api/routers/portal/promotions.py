"""Promotion workflow routes.

Ports the Java ``PromotionController`` surface for both browser and v1
clients.  Approval materializes a published copy of the source skill version
in the target namespace, reusing the existing storage keys just like Java.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query, status
from pydantic import Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from skillhub_api.deps import Principal, db_session, get_current_principal
from skillhub_api.domain.events import (
    PromotionApprovedEvent,
    PromotionRejectedEvent,
    PromotionSubmittedEvent,
    SkillPublishedEvent,
)
from skillhub_api.errors import ConflictError, DomainError, ForbiddenError, NotFoundError
from skillhub_api.events.bus import EventBus, get_event_bus
from skillhub_api.infra.db.models.auth import Role, UserRoleBinding
from skillhub_api.infra.db.models.governance import PromotionRequest
from skillhub_api.infra.db.models.namespace import Namespace, NamespaceMember
from skillhub_api.infra.db.models.skill import Skill, SkillFile, SkillVersion
from skillhub_api.infra.db.models.user import UserAccount
from skillhub_api.schemas.base import ApiModel

router = APIRouter(prefix="/api/v1/promotions", tags=["governance"])
web_router = APIRouter(prefix="/api/web/promotions", tags=["governance"])


class PromotionSubmitRequest(ApiModel):
    source_skill_id: int
    source_version_id: int
    target_namespace_id: int


class PromotionActionRequest(ApiModel):
    comment: str | None = Field(default=None, max_length=2000)


class PromotionResponse(ApiModel):
    id: int
    source_skill_id: int
    source_namespace: str | None = None
    source_skill_slug: str | None = None
    source_version: str | None = None
    target_namespace: str | None = None
    target_skill_id: int | None = None
    status: str
    submitted_by: str
    submitted_by_name: str | None = None
    reviewed_by: str | None = None
    reviewed_by_name: str | None = None
    review_comment: str | None = None
    submitted_at: datetime
    reviewed_at: datetime | None = None


class PromotionPage(ApiModel):
    items: list[PromotionResponse]
    total: int
    page: int
    size: int
    limit: int
    offset: int


def _bus_dep() -> EventBus:
    return get_event_bus()


async def _platform_roles(db: AsyncSession, user_id: str) -> set[str]:
    stmt = (
        select(Role.code)
        .join(UserRoleBinding, UserRoleBinding.role_id == Role.id)
        .where(UserRoleBinding.user_id == user_id)
    )
    return set((await db.execute(stmt)).scalars())


async def _member_role(db: AsyncSession, namespace_id: int, user_id: str) -> str | None:
    stmt = (
        select(NamespaceMember.role)
        .where(NamespaceMember.namespace_id == namespace_id)
        .where(NamespaceMember.user_id == user_id)
        .limit(1)
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def _can_review(db: AsyncSession, principal: Principal) -> bool:
    roles = await _platform_roles(db, principal.user_id)
    return bool({"SUPER_ADMIN", "SKILL_ADMIN"} & roles)


async def _require_reviewer(db: AsyncSession, principal: Principal) -> None:
    if not await _can_review(db, principal):
        raise ForbiddenError("PROMOTION_PERMISSION_DENIED", "promotion reviewer access required")


async def _can_submit(db: AsyncSession, skill: Skill, principal: Principal) -> bool:
    if skill.owner_id == principal.user_id:
        return True
    roles = await _platform_roles(db, principal.user_id)
    if {"SUPER_ADMIN", "SKILL_ADMIN"} & roles:
        return True
    role = await _member_role(db, skill.namespace_id, principal.user_id)
    return role in {"OWNER", "ADMIN"}


async def _load_promotion(db: AsyncSession, promotion_id: int) -> PromotionRequest:
    row = await db.get(PromotionRequest, promotion_id)
    if row is None:
        raise NotFoundError("PROMOTION_NOT_FOUND", f"promotion {promotion_id} not found")
    return row


async def _promotion_dto(db: AsyncSession, row: PromotionRequest) -> PromotionResponse:
    skill = await db.get(Skill, row.source_skill_id)
    version = await db.get(SkillVersion, row.source_version_id)
    source_ns = await db.get(Namespace, skill.namespace_id) if skill else None
    target_ns = await db.get(Namespace, row.target_namespace_id)
    submitted_by = await db.get(UserAccount, row.submitted_by)
    reviewed_by = await db.get(UserAccount, row.reviewed_by) if row.reviewed_by else None
    return PromotionResponse(
        id=row.id,
        source_skill_id=row.source_skill_id,
        source_namespace=source_ns.slug if source_ns else None,
        source_skill_slug=skill.slug if skill else None,
        source_version=version.version if version else None,
        target_namespace=target_ns.slug if target_ns else None,
        target_skill_id=row.target_skill_id,
        status=row.status,
        submitted_by=row.submitted_by,
        submitted_by_name=submitted_by.display_name if submitted_by else None,
        reviewed_by=row.reviewed_by,
        reviewed_by_name=reviewed_by.display_name if reviewed_by else None,
        review_comment=row.review_comment,
        submitted_at=row.submitted_at,
        reviewed_at=row.reviewed_at,
    )


async def _list_promotions(
    *,
    status_filter: str,
    page: int,
    size: int,
    principal: Principal,
    db: AsyncSession,
) -> PromotionPage:
    await _require_reviewer(db, principal)
    clean_status = status_filter.strip().upper()
    base = select(PromotionRequest).where(PromotionRequest.status == clean_status)
    total = int((await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one())
    rows = list(
        (
            await db.execute(
                base.order_by(PromotionRequest.submitted_at.desc(), PromotionRequest.id.desc())
                .offset(page * size)
                .limit(size)
            )
        ).scalars()
    )
    return PromotionPage(
        items=[await _promotion_dto(db, row) for row in rows],
        total=total,
        page=page,
        size=size,
        limit=size,
        offset=page * size,
    )


@router.get("", response_model=PromotionPage)
@web_router.get("", response_model=PromotionPage)
async def list_promotions(
    status: str = Query(default="PENDING"),
    page: int = Query(default=0, ge=0),
    size: int = Query(default=20, ge=1, le=100),
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(db_session),
) -> PromotionPage:
    return await _list_promotions(
        status_filter=status, page=page, size=size, principal=principal, db=db
    )


@router.get("/pending", response_model=PromotionPage)
@web_router.get("/pending", response_model=PromotionPage)
async def list_pending_promotions(
    page: int = Query(default=0, ge=0),
    size: int = Query(default=20, ge=1, le=100),
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(db_session),
) -> PromotionPage:
    return await _list_promotions(
        status_filter="PENDING", page=page, size=size, principal=principal, db=db
    )


@router.get("/{id}", response_model=PromotionResponse)
@web_router.get("/{id}", response_model=PromotionResponse)
async def get_promotion_detail(
    id: int,
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(db_session),
) -> PromotionResponse:
    row = await _load_promotion(db, id)
    if row.submitted_by != principal.user_id and not await _can_review(db, principal):
        raise ForbiddenError("PROMOTION_PERMISSION_DENIED", "promotion access denied")
    return await _promotion_dto(db, row)


@router.post("", response_model=PromotionResponse, status_code=status.HTTP_201_CREATED)
@web_router.post("", response_model=PromotionResponse, status_code=status.HTTP_201_CREATED)
async def submit_promotion(
    body: PromotionSubmitRequest,
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(db_session),
    bus: EventBus = Depends(_bus_dep),
) -> PromotionResponse:
    skill = await db.get(Skill, body.source_skill_id)
    if skill is None:
        raise NotFoundError("SKILL_NOT_FOUND", "source skill not found")
    version = await db.get(SkillVersion, body.source_version_id)
    if version is None or version.skill_id != skill.id:
        raise NotFoundError("VERSION_NOT_FOUND", "source version not found for source skill")
    if version.status != "PUBLISHED":
        raise DomainError("PROMOTION_VERSION_NOT_PUBLISHED", "source version must be published")
    source_ns = await db.get(Namespace, skill.namespace_id)
    target_ns = await db.get(Namespace, body.target_namespace_id)
    if source_ns is None or source_ns.status != "ACTIVE":
        raise DomainError("SOURCE_NAMESPACE_NOT_ACTIVE", "source namespace must be active")
    if target_ns is None:
        raise NotFoundError("NAMESPACE_NOT_FOUND", "target namespace not found")
    if target_ns.type != "GLOBAL":
        raise DomainError("PROMOTION_TARGET_NOT_GLOBAL", "target namespace must be global")
    if not await _can_submit(db, skill, principal):
        raise ForbiddenError("PROMOTION_PERMISSION_DENIED", "promotion submit access denied")

    duplicate = (
        await db.execute(
            select(PromotionRequest)
            .where(PromotionRequest.source_skill_id == skill.id)
            .where(PromotionRequest.status.in_(["PENDING", "APPROVED"]))
            .limit(1)
        )
    ).scalar_one_or_none()
    if duplicate is not None:
        raise ConflictError("PROMOTION_DUPLICATE", "promotion already pending or approved")

    row = PromotionRequest(
        source_skill_id=skill.id,
        source_version_id=version.id,
        target_namespace_id=target_ns.id,
        submitted_by=principal.user_id,
        status="PENDING",
    )
    db.add(row)
    await db.flush()
    bus.enqueue(
        PromotionSubmittedEvent(
            occurred_at=datetime.now(UTC),
            skill_id=skill.id,
            version_id=version.id,
            promotion_id=row.id,
            submitter_id=principal.user_id,
        )
    )
    await db.commit()
    return await _promotion_dto(db, row)


@router.post("/{id}/approve", response_model=PromotionResponse)
@web_router.post("/{id}/approve", response_model=PromotionResponse)
async def approve_promotion(
    id: int,
    body: PromotionActionRequest | None = None,
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(db_session),
    bus: EventBus = Depends(_bus_dep),
) -> PromotionResponse:
    await _require_reviewer(db, principal)
    row = await _load_promotion(db, id)
    if row.status != "PENDING":
        raise ConflictError("PROMOTION_NOT_PENDING", f"promotion already {row.status}")
    source_skill = await db.get(Skill, row.source_skill_id)
    source_version = await db.get(SkillVersion, row.source_version_id)
    if source_skill is None or source_version is None:
        raise NotFoundError("PROMOTION_SOURCE_NOT_FOUND", "promotion source no longer exists")

    target_skill = Skill(
        namespace_id=row.target_namespace_id,
        slug=source_skill.slug,
        display_name=source_skill.display_name,
        summary=source_skill.summary,
        owner_id=source_skill.owner_id,
        source_skill_id=source_skill.id,
        visibility="PUBLIC",
        status="ACTIVE",
        created_by=principal.user_id,
        updated_by=principal.user_id,
    )
    db.add(target_skill)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise ConflictError("PROMOTION_TARGET_SKILL_CONFLICT", "target skill already exists") from exc

    target_version = SkillVersion(
        skill_id=target_skill.id,
        version=source_version.version,
        status="PUBLISHED",
        changelog=source_version.changelog,
        parsed_metadata_json=source_version.parsed_metadata_json,
        manifest_json=source_version.manifest_json,
        file_count=source_version.file_count,
        total_size=source_version.total_size,
        bundle_ready=source_version.bundle_ready,
        download_ready=source_version.download_ready,
        requested_visibility="PUBLIC",
        published_at=datetime.now(UTC),
        created_by=source_version.created_by,
    )
    db.add(target_version)
    await db.flush()
    for source_file in (
        await db.execute(
            select(SkillFile)
            .where(SkillFile.version_id == source_version.id)
            .order_by(SkillFile.file_path.asc())
        )
    ).scalars():
        db.add(
            SkillFile(
                version_id=target_version.id,
                file_path=source_file.file_path,
                file_size=source_file.file_size,
                content_type=source_file.content_type,
                sha256=source_file.sha256,
                storage_key=source_file.storage_key,
            )
        )
    target_skill.latest_version_id = target_version.id
    now = datetime.now(UTC)
    row.status = "APPROVED"
    row.reviewed_by = principal.user_id
    row.reviewed_at = now
    row.review_comment = body.comment if body else None
    row.target_skill_id = target_skill.id
    bus.enqueue(
        SkillPublishedEvent(
            occurred_at=now,
            skill_id=target_skill.id,
            version_id=target_version.id,
            publisher_id=principal.user_id,
        )
    )
    bus.enqueue(
        PromotionApprovedEvent(
            occurred_at=now,
            skill_id=source_skill.id,
            promotion_id=row.id,
            reviewer_id=principal.user_id,
            submitter_id=row.submitted_by,
        )
    )
    await db.commit()
    return await _promotion_dto(db, row)


@router.post("/{id}/reject", response_model=PromotionResponse)
@web_router.post("/{id}/reject", response_model=PromotionResponse)
async def reject_promotion(
    id: int,
    body: PromotionActionRequest | None = None,
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(db_session),
    bus: EventBus = Depends(_bus_dep),
) -> PromotionResponse:
    await _require_reviewer(db, principal)
    row = await _load_promotion(db, id)
    if row.status != "PENDING":
        raise ConflictError("PROMOTION_NOT_PENDING", f"promotion already {row.status}")
    now = datetime.now(UTC)
    row.status = "REJECTED"
    row.reviewed_by = principal.user_id
    row.reviewed_at = now
    row.review_comment = body.comment if body else None
    bus.enqueue(
        PromotionRejectedEvent(
            occurred_at=now,
            skill_id=row.source_skill_id,
            promotion_id=row.id,
            reviewer_id=principal.user_id,
            submitter_id=row.submitted_by,
            reason=row.review_comment,
        )
    )
    await db.commit()
    return await _promotion_dto(db, row)
