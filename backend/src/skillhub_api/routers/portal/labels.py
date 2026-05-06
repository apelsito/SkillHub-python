"""Public label listing plus skill label attach/detach."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from skillhub_api.deps import Principal, db_session, get_current_principal
from skillhub_api.errors import ForbiddenError
from skillhub_api.infra.db.models.label import LabelDefinition, LabelTranslation
from skillhub_api.infra.repositories.label import LabelTranslationRepository
from skillhub_api.schemas.admin import SkillLabelDto
from skillhub_api.services.labels import LabelDefinitionService, SkillLabelService
from skillhub_api.services.skills.query import SkillQueryService

public_router = APIRouter(tags=["labels"])
binding_router = APIRouter(prefix="/api/v1/skills/{namespace}/{slug}/labels", tags=["labels"])
binding_web_router = APIRouter(prefix="/api/web/skills/{namespace}/{slug}/labels", tags=["labels"])


def _pick_locale(translations: list[LabelTranslation], accept_language: str | None) -> str:
    if accept_language:
        tag = accept_language.split(",", 1)[0].strip().lower()
        for translation in translations:
            if translation.locale.lower() == tag:
                return translation.display_name
    for translation in translations:
        if translation.locale.lower() in ("en", "en-us"):
            return translation.display_name
    if translations:
        return translations[0].display_name
    return ""


def _to_public_label_dto(
    definition: LabelDefinition,
    translations: list[LabelTranslation],
    accept_language: str | None,
) -> SkillLabelDto:
    return SkillLabelDto(
        slug=definition.slug,
        type=definition.type,
        display_name=_pick_locale(translations, accept_language) or definition.slug,
    )


def _to_skill_label_dto(
    definition: LabelDefinition, translations: list[LabelTranslation]
) -> SkillLabelDto:
    display = translations[0].display_name if translations else definition.slug
    return SkillLabelDto(slug=definition.slug, type=definition.type, display_name=display)


@public_router.get("/api/v1/labels", response_model=list[SkillLabelDto])
@public_router.get("/api/web/labels", response_model=list[SkillLabelDto])
async def list_labels(
    accept_language: str | None = Header(default=None, alias="Accept-Language"),
    db: AsyncSession = Depends(db_session),
) -> list[SkillLabelDto]:
    svc = LabelDefinitionService(db)
    rows = await svc.list_visible()
    return [
        _to_public_label_dto(definition, translations, accept_language)
        for definition, translations in rows
    ]


@binding_router.get("", response_model=list[SkillLabelDto])
@binding_web_router.get("", response_model=list[SkillLabelDto])
async def list_skill_labels(
    namespace: str,
    slug: str,
    db: AsyncSession = Depends(db_session),
) -> list[SkillLabelDto]:
    query_svc = SkillQueryService(db)
    skill = await query_svc.get_skill(namespace, slug)
    svc = SkillLabelService(db)
    rows = await svc.list_for_skill(skill.id)
    trans_repo = LabelTranslationRepository(db)
    trans_by_label = await trans_repo.list_for_labels([definition.id for _, definition in rows])
    return [
        _to_skill_label_dto(definition, trans_by_label.get(definition.id, []))
        for _, definition in rows
    ]


@binding_router.put("/{labelSlug}", response_model=SkillLabelDto)
@binding_web_router.put("/{labelSlug}", response_model=SkillLabelDto)
async def attach_label(
    namespace: str,
    slug: str,
    labelSlug: str,
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(db_session),
) -> SkillLabelDto:
    query_svc = SkillQueryService(db)
    skill = await query_svc.get_skill(namespace, slug)
    if skill.owner_id != principal.user_id:
        raise ForbiddenError("NOT_SKILL_OWNER", "only the skill owner can manage labels")
    svc = SkillLabelService(db)
    _, definition = await svc.attach(
        skill_id=skill.id, label_slug=labelSlug, actor_id=principal.user_id
    )
    await db.commit()
    trans_repo = LabelTranslationRepository(db)
    translations = await trans_repo.list_for_label(definition.id)
    return _to_skill_label_dto(definition, translations)


@binding_router.delete("/{labelSlug}", status_code=status.HTTP_204_NO_CONTENT)
@binding_web_router.delete("/{labelSlug}", status_code=status.HTTP_204_NO_CONTENT)
async def detach_label(
    namespace: str,
    slug: str,
    labelSlug: str,
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(db_session),
) -> Response:
    query_svc = SkillQueryService(db)
    skill = await query_svc.get_skill(namespace, slug)
    if skill.owner_id != principal.user_id:
        raise ForbiddenError("NOT_SKILL_OWNER", "only the skill owner can manage labels")
    svc = SkillLabelService(db)
    await svc.detach(skill_id=skill.id, label_slug=labelSlug)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
