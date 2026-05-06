"""Admin label CRUD — /api/v1/admin/labels/*."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from skillhub_api.deps import Principal, db_session, require_any_role
from skillhub_api.infra.db.models.label import LabelDefinition, LabelTranslation
from skillhub_api.schemas.admin import (
    AdminLabelCreateRequest,
    AdminLabelUpdateRequest,
    LabelDefinitionListResponse,
    LabelDefinitionResponse,
    LabelSortOrderUpdate,
    LabelTranslationItem,
)
from skillhub_api.services.labels import LabelDefinitionService

router = APIRouter(prefix="/api/v1/admin/labels", tags=["admin"])


def _dto(
    definition: LabelDefinition, translations: list[LabelTranslation]
) -> LabelDefinitionResponse:
    return LabelDefinitionResponse(
        id=definition.id,
        slug=definition.slug,
        type=definition.type,
        visible_in_filter=definition.visible_in_filter,
        sort_order=definition.sort_order,
        translations=[
            LabelTranslationItem(locale=t.locale, display_name=t.display_name) for t in translations
        ],
    )


@router.get("", response_model=LabelDefinitionListResponse)
async def list_labels(
    _principal: Principal = Depends(require_any_role("SUPER_ADMIN")),
    db: AsyncSession = Depends(db_session),
) -> LabelDefinitionListResponse:
    svc = LabelDefinitionService(db)
    rows = await svc.list_all()
    return LabelDefinitionListResponse(items=[_dto(d, t) for d, t in rows])


@router.post(
    "",
    response_model=LabelDefinitionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_label(
    body: AdminLabelCreateRequest,
    principal: Principal = Depends(require_any_role("SUPER_ADMIN")),
    db: AsyncSession = Depends(db_session),
) -> LabelDefinitionResponse:
    svc = LabelDefinitionService(db)
    row, translations = await svc.create(
        slug=body.slug,
        type_=body.type,
        visible_in_filter=body.visible_in_filter,
        sort_order=body.sort_order,
        translations=[t.model_dump() for t in body.translations],
        created_by=principal.user_id,
    )
    await db.commit()
    return _dto(row, translations)


@router.put("/{slug}", response_model=LabelDefinitionResponse)
async def update_label(
    slug: str,
    body: AdminLabelUpdateRequest,
    _principal: Principal = Depends(require_any_role("SUPER_ADMIN")),
    db: AsyncSession = Depends(db_session),
) -> LabelDefinitionResponse:
    svc = LabelDefinitionService(db)
    row, translations = await svc.update(
        slug,
        type_=body.type,
        visible_in_filter=body.visible_in_filter,
        sort_order=body.sort_order,
        translations=[t.model_dump() for t in body.translations] if body.translations else None,
    )
    await db.commit()
    return _dto(row, translations)


@router.delete("/{slug}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_label(
    slug: str,
    _principal: Principal = Depends(require_any_role("SUPER_ADMIN")),
    db: AsyncSession = Depends(db_session),
) -> Response:
    svc = LabelDefinitionService(db)
    await svc.delete(slug)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/sort-order", response_model=LabelDefinitionListResponse)
async def update_sort_order(
    body: LabelSortOrderUpdate,
    _principal: Principal = Depends(require_any_role("SUPER_ADMIN")),
    db: AsyncSession = Depends(db_session),
) -> LabelDefinitionListResponse:
    svc = LabelDefinitionService(db)
    rows = await svc.update_sort_order([e.model_dump() for e in body.entries])
    await db.commit()
    return LabelDefinitionListResponse(items=[_dto(d, t) for d, t in rows])
