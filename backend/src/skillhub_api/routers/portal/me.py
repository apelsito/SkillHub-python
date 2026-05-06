"""Dashboard-scoped endpoints for the current user.

Ports a thinned ``MeController`` + the ``my-namespaces`` GET from
``NamespaceController``. Matches the URL shape the frontend expects
(``/api/v1/me/...`` and ``/api/web/me/...``) so the dashboard can load
without 404s.

Listings are paginated with a ``PageResponse``-style wrapper
(``{items, total, page, size}``). Real filter/sort parity with Java lands
later; for now we return the user's owned / starred / subscribed rows
using the existing repos.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from skillhub_api.deps import Principal, db_session, get_current_principal
from skillhub_api.infra.db.models.namespace import Namespace, NamespaceMember
from skillhub_api.infra.db.models.skill import Skill, SkillVersion
from skillhub_api.infra.db.models.social import SkillStar, SkillSubscription

# Two routers so the frontend can hit either prefix. They share handlers.
router_v1 = APIRouter(prefix="/api/v1/me", tags=["me"])
router_web = APIRouter(prefix="/api/web/me", tags=["me"])


def _page(items: list, total: int, page: int, size: int) -> dict:
    return {"items": items, "total": total, "page": page, "size": size}


def _version_dto(row: SkillVersion | None) -> dict | None:
    if row is None:
        return None
    return {"id": row.id, "version": row.version, "status": row.status, "publishedAt": row.published_at}


async def _skill_dto(db: AsyncSession, row: Skill) -> dict:
    namespace = await db.get(Namespace, row.namespace_id)
    latest_version = await db.get(SkillVersion, row.latest_version_id) if row.latest_version_id else None
    lifecycle = _version_dto(latest_version)
    return {
        "id": row.id,
        "namespaceId": row.namespace_id,
        "namespace": namespace.slug if namespace else None,
        "slug": row.slug,
        "displayName": row.display_name,
        "summary": row.summary,
        "ownerId": row.owner_id,
        "visibility": row.visibility,
        "status": row.status,
        "latestVersionId": row.latest_version_id,
        "downloadCount": row.download_count,
        "starCount": row.star_count,
        "ratingAvg": float(row.rating_avg),
        "ratingCount": row.rating_count,
        "hidden": row.hidden,
        "createdAt": row.created_at.isoformat().replace("+00:00", "Z"),
        "updatedAt": row.updated_at.isoformat().replace("+00:00", "Z"),
        "canSubmitPromotion": False,
        "canManageLifecycle": True,
        "canInteract": True,
        "canReport": True,
        "headlineVersion": lifecycle,
        "publishedVersion": lifecycle if latest_version and latest_version.status == "PUBLISHED" else None,
        "ownerPreviewVersion": lifecycle,
        "resolutionMode": "OWNER",
    }


async def _list_my_skills(
    db: AsyncSession,
    user_id: str,
    *,
    page: int,
    size: int,
) -> dict:
    base = select(Skill).where(Skill.owner_id == user_id)
    total = int(
        (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    )
    rows = list(
        (
            await db.execute(
                base.order_by(Skill.updated_at.desc()).offset(page * size).limit(size)
            )
        ).scalars()
    )
    return _page([await _skill_dto(db, r) for r in rows], total, page, size)


async def _list_my_starred(
    db: AsyncSession,
    user_id: str,
    *,
    page: int,
    size: int,
) -> dict:
    base = (
        select(Skill)
        .join(SkillStar, SkillStar.skill_id == Skill.id)
        .where(SkillStar.user_id == user_id)
    )
    total = int(
        (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    )
    rows = list(
        (
            await db.execute(
                base.order_by(SkillStar.created_at.desc()).offset(page * size).limit(size)
            )
        ).scalars()
    )
    return _page([await _skill_dto(db, r) for r in rows], total, page, size)


async def _list_my_subscriptions(
    db: AsyncSession,
    user_id: str,
    *,
    page: int,
    size: int,
) -> dict:
    base = (
        select(Skill)
        .join(SkillSubscription, SkillSubscription.skill_id == Skill.id)
        .where(SkillSubscription.user_id == user_id)
    )
    total = int(
        (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    )
    rows = list(
        (
            await db.execute(
                base.order_by(SkillSubscription.created_at.desc())
                .offset(page * size)
                .limit(size)
            )
        ).scalars()
    )
    return _page([await _skill_dto(db, r) for r in rows], total, page, size)


async def _list_my_namespaces(db: AsyncSession, user_id: str) -> list[dict]:
    # Owner always has access to the bootstrap `global` namespace as a
    # reader; membership rows drive everything else.
    stmt = (
        select(Namespace, NamespaceMember.role)
        .join(
            NamespaceMember,
            and_(
                NamespaceMember.namespace_id == Namespace.id,
                NamespaceMember.user_id == user_id,
            ),
        )
        .order_by(Namespace.slug.asc())
    )
    rows = list((await db.execute(stmt)).all())
    return [
        {
            "id": ns.id,
            "slug": ns.slug,
            "displayName": ns.display_name,
            "type": ns.type,
            "status": ns.status,
            "role": role,
        }
        for ns, role in rows
    ]


@router_v1.get("/skills")
@router_web.get("/skills")
async def list_my_skills(
    page: int = Query(default=0, ge=0),
    size: int = Query(default=10, ge=1, le=100),
    filter: str | None = Query(default=None),
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(db_session),
) -> dict:
    _ = filter  # TODO: wire filter (search by slug/displayName) when the UI needs it
    return await _list_my_skills(db, principal.user_id, page=page, size=size)


@router_v1.get("/stars")
@router_web.get("/stars")
async def list_my_stars(
    page: int = Query(default=0, ge=0),
    size: int = Query(default=12, ge=1, le=100),
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(db_session),
) -> dict:
    return await _list_my_starred(db, principal.user_id, page=page, size=size)


@router_v1.get("/subscriptions")
@router_web.get("/subscriptions")
async def list_my_subscriptions(
    page: int = Query(default=0, ge=0),
    size: int = Query(default=12, ge=1, le=100),
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(db_session),
) -> dict:
    return await _list_my_subscriptions(db, principal.user_id, page=page, size=size)


@router_v1.get("/namespaces")
@router_web.get("/namespaces")
async def list_my_namespaces(
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(db_session),
) -> list[dict]:
    return await _list_my_namespaces(db, principal.user_id)
