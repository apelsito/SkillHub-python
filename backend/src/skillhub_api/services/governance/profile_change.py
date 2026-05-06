"""Profile change request workflow.

Stripped port of ``ProfileChangeService.java``. Users propose edits; the
machine-review flag decides whether to fast-track simple changes;
human reviewers approve or reject.

Fields governed by this workflow are limited to ``display_name`` and
``avatar_url`` for now — email changes follow a separate flow in Java
that we'll port in Phase 7.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from skillhub_api.domain.events import (
    ProfileChangeApprovedEvent,
    ProfileChangeRejectedEvent,
    ProfileChangeSubmittedEvent,
)
from skillhub_api.errors import ConflictError, ForbiddenError, NotFoundError
from skillhub_api.events.bus import EventBus
from skillhub_api.infra.db.models.auth import ProfileChangeRequest
from skillhub_api.infra.db.models.user import UserAccount
from skillhub_api.infra.repositories.user import UserRepository
from skillhub_api.settings import get_settings

EDITABLE_FIELDS = {"display_name", "avatar_url"}


class ProfileChangeService:
    def __init__(self, session: AsyncSession, bus: EventBus) -> None:
        self._session = session
        self._bus = bus
        self._users = UserRepository(session)

    async def submit(
        self,
        *,
        user_id: str,
        changes: dict[str, Any],
    ) -> ProfileChangeRequest:
        if not changes:
            raise ConflictError("EMPTY_CHANGES", "at least one change is required")
        unknown = set(changes) - EDITABLE_FIELDS
        if unknown:
            raise ConflictError("UNKNOWN_FIELDS", f"fields not editable: {sorted(unknown)}")

        user = await self._users.get(user_id)
        if user is None:  # pragma: no cover — authenticated users exist
            raise NotFoundError("USER_NOT_FOUND", "user not found")

        old_values = {k: getattr(user, k) for k in changes}
        settings = get_settings()

        row = ProfileChangeRequest(
            user_id=user_id,
            changes=changes,
            old_values=old_values,
            status="PENDING",
        )
        self._session.add(row)
        await self._session.flush()

        if not settings.profile_human_review_enabled:
            await self._apply(user, row, reviewer_id=user_id, comment="auto-approved")
            self._bus.enqueue(
                ProfileChangeApprovedEvent(
                    occurred_at=datetime.now(UTC),
                    user_id=user_id,
                    request_id=row.id,
                    reviewer_id=user_id,
                )
            )
        else:
            self._bus.enqueue(
                ProfileChangeSubmittedEvent(
                    occurred_at=datetime.now(UTC),
                    user_id=user_id,
                    request_id=row.id,
                )
            )
        return row

    async def approve(
        self, *, request_id: int, reviewer_id: str, comment: str | None = None
    ) -> ProfileChangeRequest:
        row = await self._load_pending(request_id)
        user = await self._users.get(row.user_id)
        if user is None:  # pragma: no cover
            raise NotFoundError("USER_NOT_FOUND", "user not found")
        await self._apply(user, row, reviewer_id=reviewer_id, comment=comment)
        self._bus.enqueue(
            ProfileChangeApprovedEvent(
                occurred_at=datetime.now(UTC),
                user_id=row.user_id,
                request_id=row.id,
                reviewer_id=reviewer_id,
            )
        )
        return row

    async def reject(
        self, *, request_id: int, reviewer_id: str, reason: str
    ) -> ProfileChangeRequest:
        row = await self._load_pending(request_id)
        now = datetime.now(UTC)
        row.status = "REJECTED"
        row.reviewer_id = reviewer_id
        row.review_comment = reason
        row.reviewed_at = now
        self._bus.enqueue(
            ProfileChangeRejectedEvent(
                occurred_at=now,
                user_id=row.user_id,
                request_id=row.id,
                reviewer_id=reviewer_id,
                reason=reason,
            )
        )
        return row

    async def _apply(
        self,
        user: UserAccount,
        row: ProfileChangeRequest,
        *,
        reviewer_id: str,
        comment: str | None,
    ) -> None:
        now = datetime.now(UTC)
        for key, value in row.changes.items():
            setattr(user, key, value)
        user.updated_at = now
        row.status = "APPROVED"
        row.reviewer_id = reviewer_id
        row.review_comment = comment
        row.reviewed_at = now
        await self._session.flush()

    async def _load_pending(self, request_id: int) -> ProfileChangeRequest:
        row = await self._session.get(ProfileChangeRequest, request_id)
        if row is None:
            raise NotFoundError("REQUEST_NOT_FOUND", f"request {request_id} not found")
        if row.status != "PENDING":
            raise ForbiddenError("REQUEST_NOT_PENDING", f"request already {row.status}")
        return row
