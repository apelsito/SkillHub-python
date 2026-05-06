"""Admin compatibility routes for promotion requests."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from skillhub_api.deps import Principal, db_session, require_permission
from skillhub_api.events.bus import EventBus, get_event_bus
from skillhub_api.infra.repositories.governance import PromotionRequestRepository
from skillhub_api.routers.portal.promotions import (
    PromotionActionRequest,
    PromotionResponse,
    approve_promotion as portal_approve_promotion,
    reject_promotion as portal_reject_promotion,
)

router = APIRouter(prefix="/api/v1/admin/promotions", tags=["admin"])


def _bus_dep() -> EventBus:
    return get_event_bus()


@router.get("")
async def list_pending(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _principal: Principal = Depends(require_permission("promotion:approve")),
    db: AsyncSession = Depends(db_session),
) -> dict:
    repo = PromotionRequestRepository(db)
    rows, total = await repo.list_pending(limit=limit, offset=offset)
    return {
        "items": [
            {
                "id": r.id,
                "sourceSkillId": r.source_skill_id,
                "sourceVersionId": r.source_version_id,
                "targetNamespaceId": r.target_namespace_id,
                "status": r.status,
                "submittedBy": r.submitted_by,
                "submittedAt": r.submitted_at.isoformat().replace("+00:00", "Z"),
            }
            for r in rows
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.post("/{promotion_id}/approve", response_model=PromotionResponse)
async def approve(
    promotion_id: int,
    body: PromotionActionRequest | None = None,
    principal: Principal = Depends(require_permission("promotion:approve")),
    db: AsyncSession = Depends(db_session),
    bus: EventBus = Depends(_bus_dep),
) -> PromotionResponse:
    return await portal_approve_promotion(promotion_id, body, principal, db, bus)


@router.post("/{promotion_id}/reject", response_model=PromotionResponse)
async def reject(
    promotion_id: int,
    body: PromotionActionRequest | None = None,
    principal: Principal = Depends(require_permission("promotion:approve")),
    db: AsyncSession = Depends(db_session),
    bus: EventBus = Depends(_bus_dep),
) -> PromotionResponse:
    return await portal_reject_promotion(promotion_id, body, principal, db, bus)
