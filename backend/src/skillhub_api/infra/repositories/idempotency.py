"""Idempotency record repository."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from skillhub_api.infra.db.models.idempotency import IdempotencyRecord

# Default record retention. Matches the Java IdempotencyCleanupTask cron
# which removes records older than ~24h; the expiry drives the same cutoff.
DEFAULT_RETENTION = timedelta(hours=24)


class IdempotencyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, request_id: str) -> IdempotencyRecord | None:
        return await self._session.get(IdempotencyRecord, request_id)

    async def reserve(
        self,
        *,
        request_id: str,
        resource_type: str,
    ) -> tuple[IdempotencyRecord, bool]:
        """Insert a PROCESSING record and return (row, created).

        On conflict with an existing request_id, return the existing row
        without modification — the caller should treat a COMPLETED row as a
        cache hit.
        """
        now = datetime.now(UTC)
        stmt = (
            insert(IdempotencyRecord)
            .values(
                request_id=request_id,
                resource_type=resource_type,
                status="PROCESSING",
                created_at=now,
                expires_at=now + DEFAULT_RETENTION,
            )
            .on_conflict_do_nothing(index_elements=[IdempotencyRecord.request_id])
            .returning(IdempotencyRecord)
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        if row is not None:
            return row, True
        existing = (
            await self._session.execute(
                select(IdempotencyRecord).where(IdempotencyRecord.request_id == request_id)
            )
        ).scalar_one()
        return existing, False

    async def complete(
        self,
        record: IdempotencyRecord,
        *,
        resource_id: int | None,
        response_status_code: int,
    ) -> None:
        record.resource_id = resource_id
        record.response_status_code = response_status_code
        record.status = "COMPLETED"
        await self._session.flush()

    async def fail(self, record: IdempotencyRecord, *, response_status_code: int) -> None:
        record.response_status_code = response_status_code
        record.status = "FAILED"
        await self._session.flush()
