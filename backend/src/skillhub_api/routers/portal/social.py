"""Social routes — stars, ratings, subscriptions.

Paths mirror the Java ``SkillStar/Rating/SubscriptionController``:
``PUT|GET|DELETE /api/v1/skills/{skillId}/{star|rating|subscription}``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from skillhub_api.deps import Principal, db_session, get_current_principal
from skillhub_api.events.bus import EventBus, get_event_bus
from skillhub_api.schemas.social import BooleanResponse, RatingRequest, RatingStatusResponse
from skillhub_api.services.social.ratings import SkillRatingService
from skillhub_api.services.social.stars import SkillStarService
from skillhub_api.services.social.subscriptions import SkillSubscriptionService

router = APIRouter(prefix="/api/v1/skills/{skillId}", tags=["social"])


def _bus_dep() -> EventBus:
    return get_event_bus()


# ---------- star ----------


@router.put("/star", response_model=BooleanResponse)
async def star(
    skillId: int,
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(db_session),
    bus: EventBus = Depends(_bus_dep),
) -> BooleanResponse:
    svc = SkillStarService(db, bus)
    await svc.star(skill_id=skillId, user_id=principal.user_id)
    await db.commit()
    return BooleanResponse(value=True)


@router.delete("/star", response_model=BooleanResponse)
async def unstar(
    skillId: int,
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(db_session),
    bus: EventBus = Depends(_bus_dep),
) -> BooleanResponse:
    svc = SkillStarService(db, bus)
    removed = await svc.unstar(skill_id=skillId, user_id=principal.user_id)
    await db.commit()
    return BooleanResponse(value=removed)


@router.get("/star", response_model=BooleanResponse)
async def star_status(
    skillId: int,
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(db_session),
    bus: EventBus = Depends(_bus_dep),
) -> BooleanResponse:
    svc = SkillStarService(db, bus)
    starred = await svc.has_starred(skill_id=skillId, user_id=principal.user_id)
    return BooleanResponse(value=starred)


# ---------- rating ----------


@router.put("/rating", response_model=RatingStatusResponse, status_code=status.HTTP_200_OK)
async def rate(
    skillId: int,
    body: RatingRequest,
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(db_session),
    bus: EventBus = Depends(_bus_dep),
) -> RatingStatusResponse:
    svc = SkillRatingService(db, bus)
    row = await svc.rate(skill_id=skillId, user_id=principal.user_id, score=body.score)
    await db.commit()
    return RatingStatusResponse(score=row.score, has_rated=True)


@router.get("/rating", response_model=RatingStatusResponse)
async def rating_status(
    skillId: int,
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(db_session),
    bus: EventBus = Depends(_bus_dep),
) -> RatingStatusResponse:
    svc = SkillRatingService(db, bus)
    row = await svc.get_mine(skill_id=skillId, user_id=principal.user_id)
    if row is None:
        return RatingStatusResponse(score=0, has_rated=False)
    return RatingStatusResponse(score=row.score, has_rated=True)


# ---------- subscription ----------


@router.put("/subscription", response_model=BooleanResponse)
async def subscribe(
    skillId: int,
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(db_session),
    bus: EventBus = Depends(_bus_dep),
) -> BooleanResponse:
    svc = SkillSubscriptionService(db, bus)
    await svc.subscribe(skill_id=skillId, user_id=principal.user_id)
    await db.commit()
    return BooleanResponse(value=True)


@router.delete("/subscription", response_model=BooleanResponse)
async def unsubscribe(
    skillId: int,
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(db_session),
    bus: EventBus = Depends(_bus_dep),
) -> BooleanResponse:
    svc = SkillSubscriptionService(db, bus)
    removed = await svc.unsubscribe(skill_id=skillId, user_id=principal.user_id)
    await db.commit()
    return BooleanResponse(value=removed)


@router.get("/subscription", response_model=BooleanResponse)
async def subscription_status(
    skillId: int,
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(db_session),
    bus: EventBus = Depends(_bus_dep),
) -> BooleanResponse:
    svc = SkillSubscriptionService(db, bus)
    subscribed = await svc.is_subscribed(skill_id=skillId, user_id=principal.user_id)
    return BooleanResponse(value=subscribed)
