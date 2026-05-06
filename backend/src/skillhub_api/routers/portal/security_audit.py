"""Security audit read endpoint."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from skillhub_api.deps import Principal, db_session, get_current_principal
from skillhub_api.errors import ForbiddenError, NotFoundError
from skillhub_api.infra.db.models.auth import Role, UserRoleBinding
from skillhub_api.infra.db.models.namespace import NamespaceMember
from skillhub_api.infra.db.models.security import SecurityAudit
from skillhub_api.infra.db.models.skill import Skill, SkillVersion
from skillhub_api.schemas.base import ApiModel

router = APIRouter(prefix="/api/v1/skills/{skillId}/versions/{versionId}/security-audit", tags=["skills"])


class SecurityAuditResponse(ApiModel):
    id: int
    scan_id: str | None
    scanner_type: str
    verdict: str
    is_safe: bool
    max_severity: str | None
    findings_count: int
    findings: list[Any]
    scan_duration_seconds: float | None
    scanned_at: datetime | None
    created_at: datetime


async def _roles(db: AsyncSession, user_id: str) -> set[str]:
    stmt = (
        select(Role.code)
        .join(UserRoleBinding, UserRoleBinding.role_id == Role.id)
        .where(UserRoleBinding.user_id == user_id)
    )
    return set((await db.execute(stmt)).scalars())


async def _can_view(db: AsyncSession, skill: Skill, principal: Principal) -> bool:
    if skill.owner_id == principal.user_id:
        return True
    roles = await _roles(db, principal.user_id)
    if roles & {"SUPER_ADMIN", "SKILL_ADMIN"}:
        return True
    member_role = (
        await db.execute(
            select(NamespaceMember.role)
            .where(NamespaceMember.namespace_id == skill.namespace_id)
            .where(NamespaceMember.user_id == principal.user_id)
            .limit(1)
        )
    ).scalar_one_or_none()
    return member_role in {"OWNER", "ADMIN"} or skill.visibility == "PUBLIC"


@router.get("", response_model=list[SecurityAuditResponse])
async def get_security_audits(
    skillId: int,
    versionId: int,
    scanner_type: str | None = Query(default=None, alias="scannerType"),
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(db_session),
) -> list[SecurityAuditResponse]:
    skill = await db.get(Skill, skillId)
    version = await db.get(SkillVersion, versionId)
    if skill is None or version is None or version.skill_id != skill.id:
        raise NotFoundError("SKILL_VERSION_NOT_FOUND", "skill version not found")
    if not await _can_view(db, skill, principal):
        raise ForbiddenError("SECURITY_AUDIT_FORBIDDEN", "security audit access denied")

    stmt = (
        select(SecurityAudit)
        .where(SecurityAudit.skill_version_id == versionId)
        .where(SecurityAudit.deleted_at.is_(None))
        .order_by(SecurityAudit.created_at.desc(), SecurityAudit.id.desc())
    )
    if scanner_type:
        stmt = stmt.where(SecurityAudit.scanner_type == scanner_type)
    rows = list((await db.execute(stmt)).scalars())
    if scanner_type and rows:
        rows = rows[:1]
    return [
        SecurityAuditResponse(
            id=row.id,
            scan_id=row.scan_id,
            scanner_type=row.scanner_type,
            verdict=row.verdict,
            is_safe=row.is_safe,
            max_severity=row.max_severity,
            findings_count=row.findings_count,
            findings=row.findings or [],
            scan_duration_seconds=row.scan_duration_seconds,
            scanned_at=row.scanned_at,
            created_at=row.created_at,
        )
        for row in rows
    ]
