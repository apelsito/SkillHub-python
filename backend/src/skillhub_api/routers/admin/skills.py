"""Admin skill moderation — /api/v1/admin/skills/*."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from skillhub_api.deps import Principal, db_session, require_any_role
from skillhub_api.domain.events import SkillStatusChangedEvent, SkillVersionYankedEvent
from skillhub_api.errors import ConflictError, NotFoundError
from skillhub_api.events.bus import EventBus, get_event_bus
from skillhub_api.infra.db.models.skill import Skill, SkillVersion
from skillhub_api.schemas.admin import AdminSkillActionRequest, AdminSkillMutationResponse

router = APIRouter(prefix="/api/v1/admin/skills", tags=["admin"])


def _bus_dep() -> EventBus:
    return get_event_bus()


@router.post("/{skillId}/hide", response_model=AdminSkillMutationResponse)
async def admin_hide(
    skillId: int,
    body: AdminSkillActionRequest,
    principal: Principal = Depends(require_any_role("SUPER_ADMIN", "SKILL_ADMIN")),
    db: AsyncSession = Depends(db_session),
    bus: EventBus = Depends(_bus_dep),
) -> AdminSkillMutationResponse:
    skill = await db.get(Skill, skillId)
    if skill is None:
        raise NotFoundError("SKILL_NOT_FOUND", "skill not found")
    now = datetime.now(UTC)
    skill.hidden = True
    skill.hidden_at = now
    skill.hidden_by = principal.user_id
    skill.updated_by = principal.user_id
    # Status doesn't flip; hidden is the gate for search.
    await db.commit()
    bus.enqueue(
        SkillStatusChangedEvent(occurred_at=now, skill_id=skillId, new_status=skill.status)
    )
    return AdminSkillMutationResponse(
        skill_id=skillId, version_id=None, action="HIDE", status=skill.status
    )


@router.post("/{skillId}/unhide", response_model=AdminSkillMutationResponse)
async def admin_unhide(
    skillId: int,
    principal: Principal = Depends(require_any_role("SUPER_ADMIN", "SKILL_ADMIN")),
    db: AsyncSession = Depends(db_session),
    bus: EventBus = Depends(_bus_dep),
) -> AdminSkillMutationResponse:
    skill = await db.get(Skill, skillId)
    if skill is None:
        raise NotFoundError("SKILL_NOT_FOUND", "skill not found")
    skill.hidden = False
    skill.hidden_at = None
    skill.hidden_by = None
    skill.updated_by = principal.user_id
    await db.commit()
    bus.enqueue(
        SkillStatusChangedEvent(
            occurred_at=datetime.now(UTC), skill_id=skillId, new_status=skill.status
        )
    )
    return AdminSkillMutationResponse(
        skill_id=skillId, version_id=None, action="UNHIDE", status=skill.status
    )


@router.post(
    "/versions/{versionId}/yank",
    response_model=AdminSkillMutationResponse,
)
async def admin_yank_version(
    versionId: int,
    body: AdminSkillActionRequest,
    principal: Principal = Depends(require_any_role("SUPER_ADMIN", "SKILL_ADMIN")),
    db: AsyncSession = Depends(db_session),
    bus: EventBus = Depends(_bus_dep),
) -> AdminSkillMutationResponse:
    version = await db.get(SkillVersion, versionId)
    if version is None:
        raise NotFoundError("VERSION_NOT_FOUND", "version not found")
    if version.status == "YANKED":
        raise ConflictError("ALREADY_YANKED", "version already yanked")
    now = datetime.now(UTC)
    version.status = "YANKED"
    version.yanked_at = now
    version.yanked_by = principal.user_id
    version.yank_reason = body.reason
    version.download_ready = False
    # Clear latest pointer if this was it.
    skill = await db.get(Skill, version.skill_id)
    if skill is not None and skill.latest_version_id == version.id:
        skill.latest_version_id = None
    await db.commit()
    bus.enqueue(
        SkillVersionYankedEvent(
            occurred_at=now,
            skill_id=version.skill_id,
            version_id=version.id,
            actor_user_id=principal.user_id,
        )
    )
    return AdminSkillMutationResponse(
        skill_id=version.skill_id,
        version_id=version.id,
        action="YANK",
        status="YANKED",
    )
