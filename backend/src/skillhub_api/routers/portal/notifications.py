"""Notification endpoints — list, unread-count, mark-read, delete, preferences, SSE."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from skillhub_api.deps import Principal, db_session, get_current_principal
from skillhub_api.domain.notifications import DEFAULT_CATEGORIES, Channel
from skillhub_api.infra.db.models.notification import Notification
from skillhub_api.schemas.notifications import (
    MarkAllReadResponse,
    NotificationListResponse,
    NotificationResponse,
    PreferenceBulkUpdate,
    PreferenceEntry,
    UnreadCountResponse,
)
from skillhub_api.services.notifications.service import (
    NotificationPreferenceService,
    NotificationService,
)
from skillhub_api.sse.manager import NotificationStreamManager, get_stream_manager

router = APIRouter(tags=["notifications"])


def _response(row: Notification) -> NotificationResponse:
    return NotificationResponse(
        id=row.id,
        category=row.category,
        event_type=row.event_type,
        title=row.title,
        body_json=row.body_json,
        entity_type=row.entity_type,
        entity_id=row.entity_id,
        status=row.status,
        created_at=row.created_at,
        read_at=row.read_at,
    )


@router.get("/api/v1/notifications", response_model=NotificationListResponse)
async def list_notifications(
    category: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(db_session),
) -> NotificationListResponse:
    svc = NotificationService(db)
    rows, total = await svc.list(
        principal.user_id,
        category=category,
        status=status_filter,
        limit=limit,
        offset=offset,
    )
    return NotificationListResponse(
        items=[_response(r) for r in rows], total=total, limit=limit, offset=offset
    )


@router.get("/api/web/notifications")
async def web_list_notifications(
    category: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    page: int = Query(default=0, ge=0),
    size: int = Query(default=20, ge=1, le=100),
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(db_session),
) -> dict:
    svc = NotificationService(db)
    rows, total = await svc.list(
        principal.user_id,
        category=category,
        status=status_filter,
        limit=size,
        offset=page * size,
    )
    return {"items": [_response(r) for r in rows], "total": total, "page": page, "size": size}


@router.get("/api/v1/notifications/unread-count", response_model=UnreadCountResponse)
async def unread_count(
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(db_session),
) -> UnreadCountResponse:
    svc = NotificationService(db)
    return UnreadCountResponse(count=await svc.unread_count(principal.user_id))


@router.get("/api/web/notifications/unread-count", response_model=UnreadCountResponse)
async def web_unread_count(
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(db_session),
) -> UnreadCountResponse:
    return await unread_count(principal=principal, db=db)


@router.put("/api/v1/notifications/{id}/read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_read(
    id: int,
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(db_session),
) -> None:
    svc = NotificationService(db)
    await svc.mark_read(user_id=principal.user_id, notification_id=id)
    await db.commit()


@router.put("/api/web/notifications/{id}/read", status_code=status.HTTP_204_NO_CONTENT)
async def web_mark_read(
    id: int,
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(db_session),
) -> None:
    await mark_read(id=id, principal=principal, db=db)


@router.put("/api/v1/notifications/read-all", response_model=MarkAllReadResponse)
async def mark_all_read(
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(db_session),
) -> MarkAllReadResponse:
    svc = NotificationService(db)
    updated = await svc.mark_all_read(principal.user_id)
    await db.commit()
    return MarkAllReadResponse(updated=updated)


@router.put("/api/web/notifications/read-all")
async def web_mark_all_read(
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(db_session),
) -> dict[str, int]:
    svc = NotificationService(db)
    updated = await svc.mark_all_read(principal.user_id)
    await db.commit()
    return {"count": updated}


@router.delete("/api/v1/notifications/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_notification(
    id: int,
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(db_session),
) -> None:
    svc = NotificationService(db)
    await svc.delete(user_id=principal.user_id, notification_id=id)
    await db.commit()


@router.delete("/api/web/notifications/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def web_delete_notification(
    id: int,
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(db_session),
) -> None:
    await delete_notification(id=id, principal=principal, db=db)


# ---------- preferences ----------


@router.get("/api/v1/notification-preferences", response_model=list[PreferenceEntry])
async def list_preferences(
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(db_session),
) -> list[PreferenceEntry]:
    svc = NotificationPreferenceService(db)
    rows = await svc.list(principal.user_id)
    existing = {(r.category, r.channel): r.enabled for r in rows}
    # Default to enabled for every (category, in-app) pair when the user
    # hasn't explicitly saved a preference — matches the Java default.
    entries = [
        PreferenceEntry(
            category=c.value,
            channel=Channel.IN_APP.value,
            enabled=existing.get((c.value, Channel.IN_APP.value), True),
        )
        for c in DEFAULT_CATEGORIES
    ]
    return entries


@router.get("/api/web/notification-preferences", response_model=list[PreferenceEntry])
async def web_list_preferences(
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(db_session),
) -> list[PreferenceEntry]:
    return await list_preferences(principal=principal, db=db)


@router.put("/api/v1/notification-preferences", response_model=list[PreferenceEntry])
async def update_preferences(
    body: PreferenceBulkUpdate,
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(db_session),
) -> list[PreferenceEntry]:
    svc = NotificationPreferenceService(db)
    await svc.bulk_upsert(
        user_id=principal.user_id,
        preferences=[p.model_dump() for p in body.preferences],
    )
    await db.commit()
    return await list_preferences(principal=principal, db=db)


@router.put("/api/web/notification-preferences", response_model=list[PreferenceEntry])
async def web_update_preferences(
    body: PreferenceBulkUpdate,
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(db_session),
) -> list[PreferenceEntry]:
    return await update_preferences(body=body, principal=principal, db=db)


# ---------- SSE ----------


def _stream_manager_dep() -> NotificationStreamManager:
    return get_stream_manager()


@router.get("/api/v1/notifications/sse")
async def sse_stream(
    principal: Principal = Depends(get_current_principal),
    manager: NotificationStreamManager = Depends(_stream_manager_dep),
) -> EventSourceResponse:
    conn = await manager.connect(principal.user_id)

    async def _generator():
        try:
            async for event in manager.stream(conn):
                yield event
        finally:
            await manager.disconnect(conn)

    return EventSourceResponse(_generator())
