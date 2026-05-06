"""Profile change endpoints — user-facing submit, admin-facing approve/reject."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from skillhub_api.deps import Principal, db_session, get_current_principal, require_permission
from skillhub_api.events.bus import EventBus, get_event_bus
from skillhub_api.infra.db.models.auth import ProfileChangeRequest
from skillhub_api.schemas.governance import (
    ProfileChangeReject,
    ProfileChangeSubmit,
    ProfileChangeSummary,
)
from skillhub_api.services.governance.profile_change import ProfileChangeService

router = APIRouter(tags=["governance"])


def _bus_dep() -> EventBus:
    return get_event_bus()


def _summary(row: ProfileChangeRequest) -> ProfileChangeSummary:
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


@router.post(
    "/api/v1/me/profile-change",
    response_model=ProfileChangeSummary,
    status_code=status.HTTP_201_CREATED,
)
async def submit_profile_change(
    body: ProfileChangeSubmit,
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(db_session),
    bus: EventBus = Depends(_bus_dep),
) -> ProfileChangeSummary:
    svc = ProfileChangeService(db, bus)
    row = await svc.submit(user_id=principal.user_id, changes=body.changes)
    await db.commit()
    return _summary(row)


@router.post(
    "/api/v1/admin/profile-changes/{id}/approve",
    response_model=ProfileChangeSummary,
)
async def approve_profile_change(
    id: int,
    principal: Principal = Depends(require_permission("user:manage")),
    db: AsyncSession = Depends(db_session),
    bus: EventBus = Depends(_bus_dep),
) -> ProfileChangeSummary:
    svc = ProfileChangeService(db, bus)
    row = await svc.approve(request_id=id, reviewer_id=principal.user_id)
    await db.commit()
    return _summary(row)


@router.post(
    "/api/v1/admin/profile-changes/{id}/reject",
    response_model=ProfileChangeSummary,
)
async def reject_profile_change(
    id: int,
    body: ProfileChangeReject,
    principal: Principal = Depends(require_permission("user:manage")),
    db: AsyncSession = Depends(db_session),
    bus: EventBus = Depends(_bus_dep),
) -> ProfileChangeSummary:
    svc = ProfileChangeService(db, bus)
    row = await svc.reject(request_id=id, reviewer_id=principal.user_id, reason=body.reason)
    await db.commit()
    return _summary(row)
