"""Skill-report endpoints — user-facing submit, admin-facing list/handle.

Users can file a report on any skill; admins with ``skill:manage``
permission can list pending reports and resolve them.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from skillhub_api.deps import Principal, db_session, get_current_principal, require_permission
from skillhub_api.events.bus import EventBus, get_event_bus
from skillhub_api.infra.db.models.governance import SkillReport
from skillhub_api.schemas.governance import (
    SkillReportCreate,
    SkillReportHandle,
    SkillReportListResponse,
    SkillReportSummary,
)
from skillhub_api.services.governance.reports import SkillReportService
from skillhub_api.services.skills.query import SkillQueryService

router = APIRouter(tags=["governance"])


def _bus_dep() -> EventBus:
    return get_event_bus()


def _summary(row: SkillReport) -> SkillReportSummary:
    return SkillReportSummary(
        id=row.id,
        skill_id=row.skill_id,
        namespace_id=row.namespace_id,
        reporter_id=row.reporter_id,
        reason=row.reason,
        details=row.details,
        status=row.status,
        handled_by=row.handled_by,
        handle_comment=row.handle_comment,
        created_at=row.created_at,
        handled_at=row.handled_at,
    )


@router.post(
    "/api/v1/skills/{skillId}/reports",
    response_model=SkillReportSummary,
    status_code=status.HTTP_201_CREATED,
)
async def submit_report(
    skillId: int,
    body: SkillReportCreate,
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(db_session),
    bus: EventBus = Depends(_bus_dep),
) -> SkillReportSummary:
    svc = SkillReportService(db, bus)
    row = await svc.submit(
        skill_id=skillId,
        reporter_id=principal.user_id,
        reason=body.reason,
        details=body.details,
    )
    await db.commit()
    return _summary(row)


@router.post(
    "/api/v1/skills/{namespace}/{slug}/reports",
    response_model=SkillReportSummary,
    status_code=status.HTTP_201_CREATED,
)
async def submit_report_by_slug(
    namespace: str,
    slug: str,
    body: SkillReportCreate,
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(db_session),
    bus: EventBus = Depends(_bus_dep),
) -> SkillReportSummary:
    skill = await SkillQueryService(db).get_skill(namespace, slug)
    return await submit_report(skill.id, body, principal, db, bus)


@router.get("/api/v1/admin/skill-reports", response_model=SkillReportListResponse)
async def list_pending(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _principal: Principal = Depends(require_permission("skill:manage")),
    db: AsyncSession = Depends(db_session),
    bus: EventBus = Depends(_bus_dep),
) -> SkillReportListResponse:
    svc = SkillReportService(db, bus)
    rows, total = await svc.list_pending(limit=limit, offset=offset)
    return SkillReportListResponse(
        items=[_summary(r) for r in rows], total=total, limit=limit, offset=offset
    )


@router.post(
    "/api/v1/admin/skill-reports/{id}/handle",
    response_model=SkillReportSummary,
)
async def handle_report(
    id: int,
    body: SkillReportHandle,
    principal: Principal = Depends(require_permission("skill:manage")),
    db: AsyncSession = Depends(db_session),
    bus: EventBus = Depends(_bus_dep),
) -> SkillReportSummary:
    svc = SkillReportService(db, bus)
    row = await svc.handle(
        report_id=id,
        handler_id=principal.user_id,
        action=body.action,
        comment=body.comment,
    )
    await db.commit()
    return _summary(row)


@router.post(
    "/api/v1/admin/skill-reports/{reportId}/resolve",
    response_model=SkillReportSummary,
)
async def resolve_report(
    reportId: int,
    body: SkillReportHandle,
    principal: Principal = Depends(require_permission("skill:manage")),
    db: AsyncSession = Depends(db_session),
    bus: EventBus = Depends(_bus_dep),
) -> SkillReportSummary:
    return await handle_report(reportId, body, principal, db, bus)


@router.post(
    "/api/v1/admin/skill-reports/{reportId}/dismiss",
    response_model=SkillReportSummary,
)
async def dismiss_report(
    reportId: int,
    body: SkillReportHandle | None = None,
    principal: Principal = Depends(require_permission("skill:manage")),
    db: AsyncSession = Depends(db_session),
    bus: EventBus = Depends(_bus_dep),
) -> SkillReportSummary:
    request = body or SkillReportHandle(action="DISMISSED", comment=None)
    if request.action != "DISMISSED":
        request = SkillReportHandle(action="DISMISSED", comment=request.comment)
    return await handle_report(reportId, request, principal, db, bus)
