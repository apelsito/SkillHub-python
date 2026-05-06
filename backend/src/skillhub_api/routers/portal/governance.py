"""Browser-facing governance dashboard endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from skillhub_api.deps import Principal, db_session, require_any_role
from skillhub_api.infra.db.models.audit import AuditLog
from skillhub_api.infra.db.models.governance import PromotionRequest, ReviewTask, SkillReport
from skillhub_api.infra.db.models.namespace import Namespace
from skillhub_api.infra.db.models.notification import Notification
from skillhub_api.infra.db.models.skill import Skill, SkillVersion
from skillhub_api.infra.db.models.user import UserAccount
from skillhub_api.services.notifications.service import NotificationService

router = APIRouter(prefix="/api/web/governance", tags=["governance"])

governance_principal = require_any_role("SKILL_ADMIN", "NAMESPACE_ADMIN", "SUPER_ADMIN")


def _page(items: list[dict[str, Any]], total: int, page: int, size: int) -> dict[str, Any]:
    return {"items": items, "total": total, "page": page, "size": size}


async def _count(db: AsyncSession, stmt) -> int:
    return int((await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one())


async def _display_names(db: AsyncSession, user_ids: set[str | None]) -> dict[str, str]:
    clean_ids = {user_id for user_id in user_ids if user_id}
    if not clean_ids:
        return {}
    rows = (
        await db.execute(select(UserAccount.id, UserAccount.display_name).where(UserAccount.id.in_(clean_ids)))
    ).all()
    return {user_id: display_name for user_id, display_name in rows}


@router.get("/summary")
async def summary(
    principal: Principal = Depends(governance_principal),
    db: AsyncSession = Depends(db_session),
) -> dict[str, int]:
    pending_reviews = await _count(db, select(ReviewTask).where(ReviewTask.status == "PENDING"))
    pending_promotions = await _count(db, select(PromotionRequest).where(PromotionRequest.status == "PENDING"))
    pending_reports = await _count(db, select(SkillReport).where(SkillReport.status == "PENDING"))
    unread_notifications = await _count(
        db,
        select(Notification).where(
            Notification.recipient_id == principal.user_id,
            Notification.status == "UNREAD",
            Notification.category.in_(["REVIEW", "PROMOTION", "REPORT"]),
        ),
    )
    return {
        "pendingReviews": pending_reviews,
        "pendingPromotions": pending_promotions,
        "pendingReports": pending_reports,
        "unreadNotifications": unread_notifications,
    }


async def _review_inbox(db: AsyncSession) -> list[dict[str, Any]]:
    rows = list(
        (
            await db.execute(
                select(ReviewTask, SkillVersion, Skill, Namespace)
                .join(SkillVersion, SkillVersion.id == ReviewTask.skill_version_id)
                .join(Skill, Skill.id == SkillVersion.skill_id)
                .join(Namespace, Namespace.id == ReviewTask.namespace_id)
                .where(ReviewTask.status == "PENDING")
            )
        ).all()
    )
    return [
        {
            "type": "REVIEW",
            "id": review.id,
            "title": f"Review {namespace.slug}/{skill.slug} v{version.version}",
            "subtitle": f"Submitted by {review.submitted_by}",
            "timestamp": review.submitted_at,
            "namespace": namespace.slug,
            "skillSlug": skill.slug,
        }
        for review, version, skill, namespace in rows
    ]


async def _promotion_inbox(db: AsyncSession) -> list[dict[str, Any]]:
    rows = list(
        (
            await db.execute(
                select(PromotionRequest, Skill, SkillVersion, Namespace)
                .join(Skill, Skill.id == PromotionRequest.source_skill_id)
                .join(SkillVersion, SkillVersion.id == PromotionRequest.source_version_id)
                .join(Namespace, Namespace.id == Skill.namespace_id)
                .where(PromotionRequest.status == "PENDING")
            )
        ).all()
    )
    return [
        {
            "type": "PROMOTION",
            "id": promotion.id,
            "title": f"Promote {namespace.slug}/{skill.slug} v{version.version}",
            "subtitle": f"Submitted by {promotion.submitted_by}",
            "timestamp": promotion.submitted_at,
            "namespace": namespace.slug,
            "skillSlug": skill.slug,
        }
        for promotion, skill, version, namespace in rows
    ]


async def _report_inbox(db: AsyncSession) -> list[dict[str, Any]]:
    rows = list(
        (
            await db.execute(
                select(SkillReport, Skill, Namespace)
                .join(Skill, Skill.id == SkillReport.skill_id)
                .join(Namespace, Namespace.id == SkillReport.namespace_id)
                .where(SkillReport.status == "PENDING")
            )
        ).all()
    )
    return [
        {
            "type": "REPORT",
            "id": report.id,
            "title": f"Report for {namespace.slug}/{skill.slug}",
            "subtitle": report.reason,
            "timestamp": report.created_at,
            "namespace": namespace.slug,
            "skillSlug": skill.slug,
        }
        for report, skill, namespace in rows
    ]


@router.get("/inbox")
async def inbox(
    type_filter: str | None = Query(default=None, alias="type"),
    page: int = Query(default=0, ge=0),
    size: int = Query(default=10, ge=1, le=100),
    _principal: Principal = Depends(governance_principal),
    db: AsyncSession = Depends(db_session),
) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    if type_filter in (None, "REVIEW"):
        items.extend(await _review_inbox(db))
    if type_filter in (None, "PROMOTION"):
        items.extend(await _promotion_inbox(db))
    if type_filter in (None, "REPORT"):
        items.extend(await _report_inbox(db))
    items.sort(key=lambda item: item.get("timestamp") or "", reverse=True)
    total = len(items)
    start = page * size
    return _page(items[start : start + size], total, page, size)


@router.get("/activity")
async def activity(
    page: int = Query(default=0, ge=0),
    size: int = Query(default=10, ge=1, le=100),
    _principal: Principal = Depends(governance_principal),
    db: AsyncSession = Depends(db_session),
) -> dict[str, Any]:
    base = select(AuditLog)
    total = await _count(db, base)
    rows = list(
        (
            await db.execute(
                base.order_by(desc(AuditLog.created_at), desc(AuditLog.id)).offset(page * size).limit(size)
            )
        ).scalars()
    )
    names = await _display_names(db, {row.actor_user_id for row in rows})
    return _page(
        [
            {
                "id": row.id,
                "action": row.action,
                "actorUserId": row.actor_user_id,
                "actorDisplayName": names.get(row.actor_user_id) if row.actor_user_id else None,
                "targetType": row.target_type,
                "targetId": str(row.target_id) if row.target_id is not None else None,
                "details": None if row.detail_json is None else str(row.detail_json),
                "timestamp": row.created_at,
            }
            for row in rows
        ],
        total,
        page,
        size,
    )


def _notification_dto(row: Notification) -> dict[str, Any]:
    return {
        "id": row.id,
        "category": row.category,
        "entityType": row.entity_type,
        "entityId": row.entity_id,
        "title": row.title,
        "bodyJson": row.body_json,
        "status": row.status,
        "createdAt": row.created_at,
        "readAt": row.read_at,
    }


@router.get("/notifications")
async def notifications(
    page: int = Query(default=0, ge=0),
    size: int = Query(default=10, ge=1, le=100),
    principal: Principal = Depends(governance_principal),
    db: AsyncSession = Depends(db_session),
) -> dict[str, Any]:
    base = (
        select(Notification)
        .where(Notification.recipient_id == principal.user_id)
        .where(Notification.category.in_(["REVIEW", "PROMOTION", "REPORT"]))
    )
    total = await _count(db, base)
    rows = list(
        (
            await db.execute(
                base.order_by(desc(Notification.created_at), desc(Notification.id))
                .offset(page * size)
                .limit(size)
            )
        ).scalars()
    )
    return _page([_notification_dto(row) for row in rows], total, page, size)


@router.post("/notifications/{id}/read")
async def mark_notification_read(
    id: int,
    principal: Principal = Depends(governance_principal),
    db: AsyncSession = Depends(db_session),
) -> dict[str, Any]:
    svc = NotificationService(db)
    await svc.mark_read(user_id=principal.user_id, notification_id=id)
    await db.commit()
    row = await db.get(Notification, id)
    if row is None:
        from skillhub_api.errors import NotFoundError

        raise NotFoundError("NOTIFICATION_NOT_FOUND", "notification not found")
    return _notification_dto(row)
