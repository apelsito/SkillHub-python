"""Admin profile-change review list — /api/v1/admin/profile-reviews.

Lists pending requests for moderators. The existing approve/reject
endpoints live under the user-facing router (Phase 4) and are shared;
adding a list endpoint here gives admins the queue view they need.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from skillhub_api.deps import Principal, db_session, require_any_role
from skillhub_api.events.bus import EventBus, get_event_bus
from skillhub_api.infra.db.models.auth import ProfileChangeRequest
from skillhub_api.infra.db.models.user import UserAccount
from skillhub_api.schemas.admin import ProfileReviewListResponse, ProfileReviewSummary
from skillhub_api.schemas.governance import ProfileChangeReject, ProfileChangeSummary
from skillhub_api.services.governance.profile_change import ProfileChangeService

router = APIRouter(prefix="/api/v1/admin/profile-reviews", tags=["admin"])


def _bus_dep() -> EventBus:
    return get_event_bus()


def _change_summary(row: ProfileChangeRequest) -> ProfileChangeSummary:
    return ProfileChangeSummary(
        id=row.id,
        user_id=row.user_id,
        changes=row.changes,
        old_values=row.old_values,
        status=row.status,
        reviewer_id=row.reviewer_id,
        review_comment=row.review_comment,
        created_at=row.created_at,
        reviewed_at=row.reviewed_at,
    )


@router.get("", response_model=ProfileReviewListResponse)
async def list_profile_reviews(
    status_filter: str = Query(default="PENDING", alias="status"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _principal: Principal = Depends(require_any_role("USER_ADMIN", "SUPER_ADMIN")),
    db: AsyncSession = Depends(db_session),
) -> ProfileReviewListResponse:
    base = select(ProfileChangeRequest).where(ProfileChangeRequest.status == status_filter)
    total = int((await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one())
    rows = list(
        (
            await db.execute(
                base.order_by(ProfileChangeRequest.created_at.desc()).offset(offset).limit(limit)
            )
        ).scalars()
    )

    # Resolve display names in one round-trip.
    user_ids = {r.user_id for r in rows}
    users: dict[str, UserAccount] = {}
    if user_ids:
        for row in (
            await db.execute(select(UserAccount).where(UserAccount.id.in_(user_ids)))
        ).scalars():
            users[row.id] = row

    items = [
        ProfileReviewSummary(
            id=r.id,
            user_id=r.user_id,
            display_name=users[r.user_id].display_name if r.user_id in users else "",
            changes=r.changes,
            old_values=r.old_values,
            status=r.status,
            machine_result=r.machine_result,
            reviewer_id=r.reviewer_id,
            review_comment=r.review_comment,
            created_at=r.created_at,
            reviewed_at=r.reviewed_at,
        )
        for r in rows
    ]
    return ProfileReviewListResponse(items=items, total=total, limit=limit, offset=offset)


@router.post("/{id}/approve", response_model=ProfileChangeSummary)
async def approve_profile_review(
    id: int,
    principal: Principal = Depends(require_any_role("USER_ADMIN", "SUPER_ADMIN")),
    db: AsyncSession = Depends(db_session),
    bus: EventBus = Depends(_bus_dep),
) -> ProfileChangeSummary:
    row = await ProfileChangeService(db, bus).approve(request_id=id, reviewer_id=principal.user_id)
    await db.commit()
    return _change_summary(row)


@router.post("/{id}/reject", response_model=ProfileChangeSummary)
async def reject_profile_review(
    id: int,
    body: ProfileChangeReject,
    principal: Principal = Depends(require_any_role("USER_ADMIN", "SUPER_ADMIN")),
    db: AsyncSession = Depends(db_session),
    bus: EventBus = Depends(_bus_dep),
) -> ProfileChangeSummary:
    row = await ProfileChangeService(db, bus).reject(
        request_id=id,
        reviewer_id=principal.user_id,
        reason=body.reason,
    )
    await db.commit()
    return _change_summary(row)
