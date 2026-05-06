"""ClawHub legacy compatibility layer."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from skillhub_api.deps import (
    Principal,
    db_session,
    get_current_principal,
    get_current_principal_optional,
)
from skillhub_api.domain.skill import Visibility
from skillhub_api.events.bus import get_event_bus
from skillhub_api.infra.db.models.namespace import Namespace
from skillhub_api.infra.db.models.skill import Skill, SkillVersion
from skillhub_api.infra.storage import ObjectStorage, get_storage
from skillhub_api.services.skills.package import PackageError
from skillhub_api.services.skills.publish import SkillPublishService
from skillhub_api.services.skills.query import SkillQueryService
from skillhub_api.services.social.stars import SkillStarService

router = APIRouter(prefix="/api/v1", tags=["compat"])


def storage_dep() -> ObjectStorage:
    return get_storage()


def _canonical(namespace_slug: str, slug: str) -> str:
    return f"{namespace_slug}/{slug}"


def _split_canonical(canonical: str) -> tuple[str, str]:
    value = canonical.replace("--", "/", 1)
    parts = value.split("/", 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid canonical slug")
    return parts[0], parts[1]


@router.get("/search")
async def compat_search(
    q: str | None = Query(default=None),
    page: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(db_session),
) -> dict:
    from skillhub_api.search.query import SearchQueryService

    svc = SearchQueryService(db)
    result = await svc.search(
        keyword=q, namespace=None, sort="newest", limit=limit, offset=page * limit
    )
    enriched: list[dict] = []
    for hit in result.items:
        skill = await db.get(Skill, hit.skill_id)
        if skill is None:
            continue
        enriched.append(
            {
                "canonical_slug": _canonical(hit.namespace_slug, skill.slug),
                "title": hit.title,
                "summary": hit.summary,
            }
        )
    return {"items": enriched, "total": result.total, "page": page, "limit": limit}


@router.get("/skills")
async def compat_list_skills(
    page: int = Query(default=0, ge=0),
    limit: int = Query(default=25, ge=1, le=100),
    db: AsyncSession = Depends(db_session),
) -> dict:
    base = (
        select(Skill)
        .where(Skill.status == "ACTIVE", Skill.hidden.is_(False))
        .order_by(Skill.updated_at.desc())
    )
    total = int((await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one())
    rows = list((await db.execute(base.offset(page * limit).limit(limit))).scalars())

    namespace_ids = {r.namespace_id for r in rows}
    ns_by_id = {
        n.id: n.slug
        for n in (
            await db.execute(select(Namespace).where(Namespace.id.in_(namespace_ids)))
        ).scalars()
    }

    items = [
        {
            "canonical_slug": _canonical(ns_by_id.get(r.namespace_id, ""), r.slug),
            "title": r.display_name,
            "summary": r.summary,
            "download_count": r.download_count,
            "star_count": r.star_count,
        }
        for r in rows
    ]
    return {"items": items, "total": total, "page": page, "limit": limit}


@router.get("/skills/{canonicalSlug:path}")
async def compat_get_skill(
    canonicalSlug: str,
    db: AsyncSession = Depends(db_session),
) -> dict:
    namespace_slug, slug = _split_canonical(canonicalSlug)
    skill = await SkillQueryService(db).get_skill(namespace_slug, slug)
    return {
        "canonical_slug": canonicalSlug,
        "title": skill.display_name,
        "summary": skill.summary,
        "visibility": skill.visibility,
        "status": skill.status,
        "download_count": skill.download_count,
        "star_count": skill.star_count,
        "rating_avg": float(skill.rating_avg),
        "rating_count": skill.rating_count,
    }


@router.delete("/skills/{canonicalSlug:path}")
async def compat_delete_skill(
    _canonicalSlug: str,
    _principal: Principal = Depends(get_current_principal),
) -> dict:
    # Java's compat endpoint returns a successful compatibility envelope; the
    # browser lifecycle delete endpoint owns the actual destructive workflow.
    return {"ok": True}


@router.post("/skills/{canonicalSlug:path}/undelete")
async def compat_undelete_skill(
    _canonicalSlug: str,
    _principal: Principal = Depends(get_current_principal),
) -> dict:
    return {"ok": True}


@router.get("/download/{canonicalSlug:path}")
async def compat_download(
    canonicalSlug: str,
    version: str = Query(default="latest"),
) -> RedirectResponse:
    namespace_slug, slug = _split_canonical(canonicalSlug)
    target = f"/api/v1/skills/{namespace_slug}/{slug}/download"
    if version != "latest":
        target = f"/api/v1/skills/{namespace_slug}/{slug}/versions/{version}/download"
    return RedirectResponse(url=target, status_code=status.HTTP_302_FOUND)


@router.get("/download")
async def compat_download_by_query(
    slug: str = Query(...),
    version: str = Query(default="latest"),
) -> RedirectResponse:
    return await compat_download(slug, version)


@router.get("/resolve")
async def compat_resolve_by_query(
    slug: str = Query(...),
    version: str | None = Query(default=None),
    db: AsyncSession = Depends(db_session),
) -> dict:
    return await compat_resolve(slug, version or "latest", db)


@router.get("/resolve/{canonicalSlug:path}")
async def compat_resolve(
    canonicalSlug: str,
    version: str = Query(default="latest"),
    db: AsyncSession = Depends(db_session),
) -> dict:
    namespace_slug, slug = _split_canonical(canonicalSlug)
    svc = SkillQueryService(db)
    skill = await svc.get_skill(namespace_slug, slug)
    if version == "latest":
        if skill.latest_version_id is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "latest version not found")
        row = await db.get(SkillVersion, skill.latest_version_id)
    else:
        _, row = await svc.get_version(namespace_slug, slug, version)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "version not found")
    info = {"version": row.version}
    return {"match": info, "latestVersion": info}


@router.post("/stars/{canonicalSlug:path}")
async def compat_star(
    canonicalSlug: str,
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(db_session),
) -> dict:
    namespace_slug, slug = _split_canonical(canonicalSlug)
    skill = await SkillQueryService(db).get_skill(namespace_slug, slug)
    svc = SkillStarService(db, get_event_bus())
    already = await svc.has_starred(skill_id=skill.id, user_id=principal.user_id)
    await svc.star(skill_id=skill.id, user_id=principal.user_id)
    await db.commit()
    return {"ok": True, "starred": True, "alreadyStarred": already}


@router.delete("/stars/{canonicalSlug:path}")
async def compat_unstar(
    canonicalSlug: str,
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(db_session),
) -> dict:
    namespace_slug, slug = _split_canonical(canonicalSlug)
    skill = await SkillQueryService(db).get_skill(namespace_slug, slug)
    svc = SkillStarService(db, get_event_bus())
    already_unstarred = not await svc.has_starred(skill_id=skill.id, user_id=principal.user_id)
    await svc.unstar(skill_id=skill.id, user_id=principal.user_id)
    await db.commit()
    return {"ok": True, "unstarred": True, "alreadyUnstarred": already_unstarred}


@router.post("/publish")
async def compat_publish(
    file: UploadFile = File(...),
    namespace: str = Form(default="global"),
    confirm_warnings: bool = Form(default=False, alias="confirmWarnings"),
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(db_session),
    storage: ObjectStorage = Depends(storage_dep),
) -> dict:
    _ = confirm_warnings
    svc = SkillPublishService(db, storage)
    try:
        result = await svc.publish(
            namespace_slug=namespace[1:] if namespace.startswith("@") else namespace,
            zip_bytes=await file.read(),
            visibility=Visibility.PUBLIC,
            owner_id=principal.user_id,
        )
    except PackageError as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    await db.commit()
    return {"ok": True, "skillId": str(result.skill.id), "versionId": str(result.version.id)}


@router.post("/skills")
async def compat_publish_skill(
    payload: str | None = Form(default=None),
    files: list[UploadFile] = File(default=[]),
    confirm_warnings: bool = Form(default=False, alias="confirmWarnings"),
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(db_session),
    storage: ObjectStorage = Depends(storage_dep),
) -> dict:
    namespace = "global"
    if payload:
        try:
            data = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid payload json") from exc
        raw_ns = data.get("namespace") or data.get("targetNamespace")
        if raw_ns:
            namespace = str(raw_ns)
        elif data.get("slug") and "--" in str(data["slug"]):
            namespace, _ = _split_canonical(str(data["slug"]))
    if not files:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "at least one file is required")
    return await compat_publish(files[0], namespace, confirm_warnings, principal, db, storage)


@router.get("/whoami")
async def compat_whoami(
    principal: Principal | None = Depends(get_current_principal_optional),
) -> dict:
    if principal is None:
        return {"authenticated": False}
    return {
        "authenticated": True,
        "user_id": principal.user_id,
        "display_name": principal.display_name,
    }
