"""Skill tags — named pointers to specific versions (e.g. ``stable``).

Distinct from labels (admin-curated metadata) — tags are user-submitted
aliases that map a human-readable name to a concrete ``skill_version``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from skillhub_api.deps import Principal, db_session, get_current_principal
from skillhub_api.errors import ConflictError, ForbiddenError, NotFoundError
from skillhub_api.infra.db.models.skill import SkillTag, SkillVersion
from skillhub_api.schemas.admin import TagDto, TagRequest
from skillhub_api.services.skills.query import SkillQueryService

router = APIRouter(prefix="/api/v1/skills/{namespace}/{slug}/tags", tags=["tags"])


def _to_dto(row: SkillTag) -> TagDto:
    return TagDto(
        id=row.id,
        tag_name=row.tag_name,
        version_id=row.version_id,
        created_at=row.created_at,
    )


@router.get("", response_model=list[TagDto])
async def list_tags(
    namespace: str,
    slug: str,
    db: AsyncSession = Depends(db_session),
) -> list[TagDto]:
    svc = SkillQueryService(db)
    skill = await svc.get_skill(namespace, slug)
    rows = list((await db.execute(select(SkillTag).where(SkillTag.skill_id == skill.id))).scalars())
    return [_to_dto(r) for r in rows]


@router.put("/{tagName}", response_model=TagDto)
async def upsert_tag(
    namespace: str,
    slug: str,
    tagName: str,
    body: TagRequest,
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(db_session),
) -> TagDto:
    query_svc = SkillQueryService(db)
    skill = await query_svc.get_skill(namespace, slug)
    if skill.owner_id != principal.user_id:
        raise ForbiddenError("NOT_SKILL_OWNER", "only the skill owner can manage tags")

    target = (
        await db.execute(
            select(SkillVersion)
            .where(SkillVersion.skill_id == skill.id)
            .where(SkillVersion.version == body.target_version)
            .limit(1)
        )
    ).scalar_one_or_none()
    if target is None:
        raise NotFoundError(
            "VERSION_NOT_FOUND",
            f"target version {body.target_version!r} not on {namespace}/{slug}",
        )

    existing = (
        await db.execute(
            select(SkillTag)
            .where(SkillTag.skill_id == skill.id)
            .where(SkillTag.tag_name == tagName)
            .limit(1)
        )
    ).scalar_one_or_none()
    if existing is None:
        row = SkillTag(
            skill_id=skill.id,
            tag_name=tagName,
            version_id=target.id,
            created_by=principal.user_id,
        )
        db.add(row)
    else:
        existing.version_id = target.id
        row = existing
    await db.commit()
    if row.id is None:  # pragma: no cover — flush populated id above
        raise ConflictError("TAG_NOT_PERSISTED", "tag row was not persisted")
    return _to_dto(row)


@router.delete("/{tagName}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tag(
    namespace: str,
    slug: str,
    tagName: str,
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(db_session),
) -> Response:
    query_svc = SkillQueryService(db)
    skill = await query_svc.get_skill(namespace, slug)
    if skill.owner_id != principal.user_id:
        raise ForbiddenError("NOT_SKILL_OWNER", "only the skill owner can manage tags")
    existing = (
        await db.execute(
            select(SkillTag)
            .where(SkillTag.skill_id == skill.id)
            .where(SkillTag.tag_name == tagName)
            .limit(1)
        )
    ).scalar_one_or_none()
    if existing is not None:
        await db.delete(existing)
        await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
