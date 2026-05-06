"""Notification + preference repositories."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from skillhub_api.infra.db.models.notification import (
    Notification,
    NotificationPreference,
)


class NotificationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        recipient_id: str,
        category: str,
        event_type: str,
        title: str,
        body_json: str | None,
        entity_type: str | None,
        entity_id: int | None,
    ) -> Notification:
        row = Notification(
            recipient_id=recipient_id,
            category=category,
            event_type=event_type,
            title=title,
            body_json=body_json,
            entity_type=entity_type,
            entity_id=entity_id,
            status="UNREAD",
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def list_for_user(
        self,
        user_id: str,
        *,
        category: str | None,
        status: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[Notification], int]:
        base = select(Notification).where(Notification.recipient_id == user_id)
        if category:
            base = base.where(Notification.category == category)
        if status:
            base = base.where(Notification.status == status)
        total = int(
            (
                await self._session.execute(select(func.count()).select_from(base.subquery()))
            ).scalar_one()
        )
        stmt = base.order_by(Notification.created_at.desc()).offset(offset).limit(limit)
        rows = list((await self._session.execute(stmt)).scalars())
        return rows, total

    async def unread_count(self, user_id: str) -> int:
        stmt = (
            select(func.count())
            .select_from(Notification)
            .where(
                and_(
                    Notification.recipient_id == user_id,
                    Notification.status == "UNREAD",
                )
            )
        )
        return int((await self._session.execute(stmt)).scalar_one())

    async def mark_read(self, *, user_id: str, notification_id: int) -> int:
        now = datetime.now(UTC)
        result = await self._session.execute(
            update(Notification)
            .where(
                and_(
                    Notification.id == notification_id,
                    Notification.recipient_id == user_id,
                    Notification.status == "UNREAD",
                )
            )
            .values(status="READ", read_at=now)
        )
        await self._session.flush()
        return result.rowcount or 0

    async def mark_all_read(self, user_id: str) -> int:
        now = datetime.now(UTC)
        result = await self._session.execute(
            update(Notification)
            .where(
                and_(
                    Notification.recipient_id == user_id,
                    Notification.status == "UNREAD",
                )
            )
            .values(status="READ", read_at=now)
        )
        await self._session.flush()
        return result.rowcount or 0


class NotificationPreferenceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_user(self, user_id: str) -> list[NotificationPreference]:
        stmt = select(NotificationPreference).where(NotificationPreference.user_id == user_id)
        return list((await self._session.execute(stmt)).scalars())

    async def upsert(
        self, *, user_id: str, category: str, channel: str, enabled: bool
    ) -> NotificationPreference:
        stmt = (
            select(NotificationPreference)
            .where(
                and_(
                    NotificationPreference.user_id == user_id,
                    NotificationPreference.category == category,
                    NotificationPreference.channel == channel,
                )
            )
            .limit(1)
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        if row is None:
            row = NotificationPreference(
                user_id=user_id, category=category, channel=channel, enabled=enabled
            )
            self._session.add(row)
        else:
            row.enabled = enabled
        await self._session.flush()
        return row
