"""Notification read/write service."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from skillhub_api.errors import ConflictError
from skillhub_api.infra.db.models.notification import Notification, NotificationPreference
from skillhub_api.infra.repositories.notification import (
    NotificationPreferenceRepository,
    NotificationRepository,
)


class NotificationService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._notifications = NotificationRepository(session)

    async def list(
        self,
        user_id: str,
        *,
        category: str | None,
        status: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[Notification], int]:
        return await self._notifications.list_for_user(
            user_id, category=category, status=status, limit=limit, offset=offset
        )

    async def unread_count(self, user_id: str) -> int:
        return await self._notifications.unread_count(user_id)

    async def mark_read(self, *, user_id: str, notification_id: int) -> int:
        return await self._notifications.mark_read(user_id=user_id, notification_id=notification_id)

    async def mark_all_read(self, user_id: str) -> int:
        return await self._notifications.mark_all_read(user_id)

    async def delete(self, *, user_id: str, notification_id: int) -> None:
        stmt = await self._session.get(Notification, notification_id)
        if stmt is None or stmt.recipient_id != user_id:
            return
        # Mirror Java: only READ notifications can be deleted.
        if stmt.status != "READ":
            raise ConflictError("NOTIFICATION_NOT_READ", "only read notifications can be deleted")
        await self._session.delete(stmt)
        await self._session.flush()


class NotificationPreferenceService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._prefs = NotificationPreferenceRepository(session)

    async def list(self, user_id: str) -> list[NotificationPreference]:
        return await self._prefs.list_for_user(user_id)

    async def bulk_upsert(
        self, *, user_id: str, preferences: list[dict]
    ) -> list[NotificationPreference]:
        result: list[NotificationPreference] = []
        for p in preferences:
            row = await self._prefs.upsert(
                user_id=user_id,
                category=p["category"],
                channel=p["channel"],
                enabled=p["enabled"],
            )
            result.append(row)
        return result
