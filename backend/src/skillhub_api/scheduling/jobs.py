"""Scheduled maintenance jobs backed by APScheduler.

Ports the Java ``@Scheduled`` tasks to an in-process ``AsyncIOScheduler``:

  * ``idempotency_cleanup`` — daily 02:00, removes expired
    ``idempotency_record`` rows older than their ``expires_at``.
  * ``idempotency_stale_cleanup`` — every 5 minutes, marks
    ``PROCESSING`` rows older than 30 minutes as ``FAILED`` (recovery
    from crashed request handlers).
  * ``storage_compensation_retry`` — every minute, retries
    ``skill_storage_delete_compensation`` rows stuck in ``PENDING``.
  * ``notification_cleanup`` — daily 03:00, drops READ notifications
    older than 90 days to keep the table bounded.

Single-instance guard: Redis ``SET NX EX`` lock per job key, so that
running N replicas of the API only fires each job once.
"""

from __future__ import annotations

import asyncio
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import text

from skillhub_api.infra.db.session import AsyncSessionLocal
from skillhub_api.infra.redis_client import get_redis
from skillhub_api.logging import get_logger

logger = get_logger(__name__)

LOCK_TTL_SECONDS = 300


async def _acquire_lock(job_key: str) -> bool:
    """Best-effort single-instance guard.

    If Redis is unreachable we fall through and let the job run anyway —
    worse to skip a scheduled cleanup than to double-execute an
    idempotent one.
    """
    try:
        redis = get_redis()
        lock_key = f"skillhub:scheduler:{job_key}"
        acquired = await redis.set(lock_key, "1", nx=True, ex=LOCK_TTL_SECONDS)
        return bool(acquired)
    except Exception as exc:  # pragma: no cover - infra failure
        logger.warning("scheduler.lock_failed", job=job_key, error=str(exc))
        return True


async def _idempotency_cleanup() -> None:
    if not await _acquire_lock("idempotency_cleanup"):
        return
    async with AsyncSessionLocal()() as session:
        result = await session.execute(
            text("DELETE FROM idempotency_record WHERE expires_at < now()")
        )
        await session.commit()
        logger.info("scheduler.idempotency_cleanup", deleted=result.rowcount or 0)


async def _idempotency_stale_cleanup() -> None:
    if not await _acquire_lock("idempotency_stale"):
        return
    cutoff = datetime.now(UTC) - timedelta(minutes=30)
    async with AsyncSessionLocal()() as session:
        result = await session.execute(
            text(
                "UPDATE idempotency_record SET status = 'FAILED' "
                "WHERE status = 'PROCESSING' AND created_at < :cutoff"
            ),
            {"cutoff": cutoff},
        )
        await session.commit()
        if result.rowcount:
            logger.info("scheduler.idempotency_stale", failed=result.rowcount)


async def _storage_compensation_retry() -> None:
    if not await _acquire_lock("storage_compensation"):
        return
    async with AsyncSessionLocal()() as session:
        # Placeholder: real implementation would iterate PENDING rows,
        # attempt storage.delete_object() for each, and mark DONE/FAILED.
        # Until the scanner/publish flow writes these rows, the query is
        # a no-op but kept scheduled to exercise the lock path.
        await session.execute(
            text(
                "UPDATE skill_storage_delete_compensation SET last_attempt_at = now() "
                "WHERE status = 'PENDING' AND (last_attempt_at IS NULL "
                "OR last_attempt_at < now() - interval '5 minutes') "
                "AND attempt_count < 10"
            )
        )
        await session.commit()


async def _notification_cleanup() -> None:
    if not await _acquire_lock("notification_cleanup"):
        return
    cutoff = datetime.now(UTC) - timedelta(days=90)
    async with AsyncSessionLocal()() as session:
        result = await session.execute(
            text("DELETE FROM notification WHERE status = 'READ' AND read_at < :cutoff"),
            {"cutoff": cutoff},
        )
        await session.commit()
        logger.info("scheduler.notification_cleanup", deleted=result.rowcount or 0)


class SchedulerManager:
    def __init__(self) -> None:
        self._scheduler: AsyncIOScheduler | None = None

    def start(self) -> None:
        if self._scheduler is not None:
            return
        sched = AsyncIOScheduler(timezone="UTC")
        sched.add_job(
            _idempotency_cleanup,
            CronTrigger(hour=2, minute=0),
            id="idempotency_cleanup",
            max_instances=1,
        )
        sched.add_job(
            _idempotency_stale_cleanup,
            IntervalTrigger(minutes=5),
            id="idempotency_stale",
            max_instances=1,
        )
        sched.add_job(
            _storage_compensation_retry,
            IntervalTrigger(minutes=1),
            id="storage_compensation",
            max_instances=1,
        )
        sched.add_job(
            _notification_cleanup,
            CronTrigger(hour=3, minute=0),
            id="notification_cleanup",
            max_instances=1,
        )
        sched.start()
        self._scheduler = sched
        logger.info("scheduler.started", jobs=[j.id for j in sched.get_jobs()])

    async def shutdown(self) -> None:
        if self._scheduler is None:
            return
        with suppress(Exception):
            self._scheduler.shutdown(wait=False)
        # Drain any in-flight tasks started by the scheduler.
        for _ in range(50):
            pending = [t for t in asyncio.all_tasks() if t.get_name().startswith("apscheduler")]
            if not pending:
                break
            await asyncio.sleep(0.05)
        self._scheduler = None

    def jobs(self) -> list[dict[str, Any]]:
        if self._scheduler is None:
            return []
        return [
            {"id": j.id, "next_run": j.next_run_time.isoformat() if j.next_run_time else None}
            for j in self._scheduler.get_jobs()
        ]


_singleton: SchedulerManager | None = None


def get_scheduler() -> SchedulerManager:
    global _singleton
    if _singleton is None:
        _singleton = SchedulerManager()
    return _singleton
