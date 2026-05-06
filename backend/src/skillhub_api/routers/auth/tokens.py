"""Personal API tokens — /api/v1/tokens."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from skillhub_api.deps import Principal, db_session, get_current_principal
from skillhub_api.infra.repositories.token import serialize_token
from skillhub_api.schemas.auth import (
    TokenCreateRequest,
    TokenCreateResponse,
    TokenExpirationUpdateRequest,
    TokenListResponse,
    TokenSummary,
)
from skillhub_api.services.auth.token_service import ApiTokenService

router = APIRouter(prefix="/api/v1/tokens", tags=["auth"])


@router.get("", response_model=TokenListResponse)
async def list_tokens(
    page: int = Query(default=0, ge=0),
    size: int = Query(default=10, ge=1, le=100),
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(db_session),
) -> TokenListResponse:
    svc = ApiTokenService(db)
    rows, total = await svc.list_active_for_user(principal.user_id, limit=size, offset=page * size)
    return TokenListResponse(
        items=[TokenSummary(**serialize_token(r)) for r in rows],
        total=total,
        page=page,
        size=size,
    )


@router.post("", response_model=TokenCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_token(
    body: TokenCreateRequest,
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(db_session),
) -> TokenCreateResponse:
    svc = ApiTokenService(db)
    row, minted = await svc.create(
        user_id=principal.user_id,
        name=body.name,
        scope=body.scope,
        expires_at=body.expires_at,
    )
    await db.commit()
    return TokenCreateResponse(
        token=minted.plaintext,
        id=row.id,
        name=row.name,
        token_prefix=row.token_prefix,
        created_at=row.created_at,
        expires_at=row.expires_at,
    )


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_token(
    id: int,
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(db_session),
) -> None:
    svc = ApiTokenService(db)
    await svc.revoke(user_id=principal.user_id, token_id=id)
    await db.commit()


@router.put("/{id}/expiration", response_model=TokenSummary)
async def update_token_expiration(
    id: int,
    body: TokenExpirationUpdateRequest,
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(db_session),
) -> TokenSummary:
    svc = ApiTokenService(db)
    row = await svc.update_expiration(
        user_id=principal.user_id,
        token_id=id,
        expires_at=body.expires_at,
    )
    await db.commit()
    return TokenSummary(**serialize_token(row))
