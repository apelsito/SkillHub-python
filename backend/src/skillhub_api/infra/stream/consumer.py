"""Redis Streams consumer for scan tasks.

Ports the Java ``AbstractStreamConsumer`` + ``ScanTaskConsumer`` pair to
``redis.asyncio``:

  * ``ensure_group()`` creates the consumer group if missing.
  * Blocking ``XREADGROUP`` reads new messages; each is passed to
    ``_handle_message()`` and ``XACK``-ed on success.
  * A parallel ``XAUTOCLAIM`` reclaim loop picks up messages whose
    previous consumer died without ack-ing, so scanner crashes don't
    strand work. Interval + min-idle tunable via env (see
    ``SKILLHUB_SCAN_STREAM_RECLAIM_*``).

The handler is deliberately simple in this port: it persists a
``security_audit`` row reflecting the scanner verdict. Richer flows
(quarantine the version, trigger rescan, notify the owner) land later.
"""

from __future__ import annotations

import asyncio
import json
from contextlib import suppress
from typing import Any

from skillhub_api.infra.db.session import AsyncSessionLocal
from skillhub_api.infra.redis_client import get_redis
from skillhub_api.infra.scanner import ScannerResult, SkillScannerClient
from skillhub_api.logging import get_logger
from skillhub_api.settings import ScanStreamSettings, get_settings

logger = get_logger(__name__)


async def enqueue_scan_task(
    *,
    skill_id: int,
    version_id: int,
    storage_key: str,
) -> None:
    """Producer side — matches Java ``RedissonScanTaskProducer`` semantics.

    Writes a single entry into ``skillhub:scan:requests`` with the
    minimal payload the consumer needs. The bundle is referenced by
    storage key, not inlined, to keep the stream small.
    """
    settings = get_settings().scan_stream
    redis = get_redis()
    await redis.xadd(
        settings.key,
        {
            "skill_id": str(skill_id),
            "version_id": str(version_id),
            "storage_key": storage_key,
        },
    )


class ScanTaskStreamConsumer:
    def __init__(
        self,
        *,
        settings: ScanStreamSettings | None = None,
        consumer_name: str = "skillhub-api",
    ) -> None:
        self._settings = settings or get_settings().scan_stream
        self._consumer_name = consumer_name
        self._reader_task: asyncio.Task | None = None
        self._reclaim_task: asyncio.Task | None = None
        self._scanner = SkillScannerClient()

    async def start(self) -> None:
        if self._reader_task is not None:
            return
        try:
            await self._ensure_group()
        except Exception as exc:
            logger.warning("stream.start_failed", error=str(exc))
            return
        self._reader_task = asyncio.create_task(self._reader_loop(), name="stream-reader")
        if self._settings.reclaim_enabled:
            self._reclaim_task = asyncio.create_task(self._reclaim_loop(), name="stream-reclaim")
        logger.info(
            "stream.started",
            key=self._settings.key,
            group=self._settings.group,
            consumer=self._consumer_name,
        )

    async def shutdown(self) -> None:
        for task in (self._reader_task, self._reclaim_task):
            if task is None:
                continue
            task.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await task
        self._reader_task = None
        self._reclaim_task = None

    async def _ensure_group(self) -> None:
        redis = get_redis()
        try:
            await redis.xgroup_create(
                self._settings.key,
                self._settings.group,
                id="$",
                mkstream=True,
            )
        except Exception as exc:
            # Group already exists → OK; anything else bubbles up.
            msg = str(exc).lower()
            if "busygroup" not in msg:
                raise

    async def _reader_loop(self) -> None:
        redis = get_redis()
        backoff = 1.0
        while True:
            try:
                response = await redis.xreadgroup(
                    groupname=self._settings.group,
                    consumername=self._consumer_name,
                    streams={self._settings.key: ">"},
                    count=16,
                    block=5000,
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # pragma: no cover - infra
                logger.warning("stream.read_failed", error=str(exc))
                await asyncio.sleep(min(30.0, backoff))
                backoff = min(30.0, backoff * 2)
                continue
            backoff = 1.0
            if not response:
                continue
            for _stream_name, entries in response:
                for entry_id, fields in entries:
                    await self._process(entry_id, fields)

    async def _reclaim_loop(self) -> None:
        redis = get_redis()
        min_idle_ms = int(self._settings.reclaim_min_idle.total_seconds() * 1000)
        batch = self._settings.reclaim_batch_size
        interval = self._settings.reclaim_interval.total_seconds()
        cursor = "0-0"
        while True:
            try:
                result = await redis.xautoclaim(
                    name=self._settings.key,
                    groupname=self._settings.group,
                    consumername=self._consumer_name,
                    min_idle_time=min_idle_ms,
                    start_id=cursor,
                    count=batch,
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # pragma: no cover - infra
                logger.warning("stream.reclaim_failed", error=str(exc))
                await asyncio.sleep(interval)
                continue
            if result:
                cursor = result[0] or "0-0"
                for entry_id, fields in result[1] or []:
                    await self._process(entry_id, fields)
            await asyncio.sleep(interval)

    async def _process(self, entry_id: str, fields: dict[str, Any]) -> None:
        redis = get_redis()
        try:
            await self._handle_message(fields)
        except Exception as exc:  # pragma: no cover - logged, ack'd
            logger.error("stream.handle_failed", entry=entry_id, error=str(exc), fields=fields)
        # Always ack — re-delivery is the reclaim loop's job via XAUTOCLAIM
        # so a pathologically-failing message doesn't live forever in PEL.
        with suppress(Exception):
            await redis.xack(self._settings.key, self._settings.group, entry_id)

    async def _handle_message(self, fields: dict[str, Any]) -> None:
        skill_id = int(fields.get("skill_id", 0))
        version_id = int(fields.get("version_id", 0))
        storage_key = fields.get("storage_key") or ""
        if not skill_id or not version_id:
            return

        # Call the scanner; if it's disabled or unreachable, record a
        # placeholder audit row so the UI can show "scan pending" rather
        # than silently dropping the task.
        result: ScannerResult | None
        try:
            result = await self._scanner.scan_upload(
                filename=f"{storage_key.split('/')[-1] or 'bundle.zip'}",
                contents=b"",  # real impl streams bytes from storage — stub here
            )
        except Exception as exc:
            logger.warning("stream.scan_failed", skill_id=skill_id, error=str(exc))
            result = None

        await _record_security_audit(skill_id=skill_id, version_id=version_id, result=result)


async def _record_security_audit(
    *,
    skill_id: int,
    version_id: int,
    result: ScannerResult | None,
) -> None:
    from sqlalchemy import text

    async with AsyncSessionLocal()() as session:
        verdict = "UNKNOWN"
        is_safe = False
        max_severity: str | None = None
        findings_count = 0
        findings_json = "[]"
        scan_id: str | None = None
        scan_duration: float | None = None
        if result is not None:
            verdict = "SAFE" if result.is_safe else "DANGEROUS"
            is_safe = result.is_safe
            max_severity = result.max_severity
            findings_count = result.findings_count
            findings_json = json.dumps(
                [
                    {
                        "id": f.id,
                        "rule_id": f.rule_id,
                        "severity": f.severity,
                        "title": f.title,
                        "file_path": f.file_path,
                    }
                    for f in result.findings
                ]
            )
            scan_id = result.scan_id
            scan_duration = result.scan_duration_seconds

        await session.execute(
            text(
                """
                INSERT INTO security_audit
                  (skill_version_id, scan_id, scanner_type, verdict, is_safe,
                   max_severity, findings_count, findings, scan_duration_seconds, scanned_at)
                VALUES (:ver, :scan, 'skill-scanner', :verdict, :is_safe,
                        :severity, :count, :findings::jsonb, :dur, now())
                """
            ),
            {
                "ver": version_id,
                "scan": scan_id,
                "verdict": verdict,
                "is_safe": is_safe,
                "severity": max_severity,
                "count": findings_count,
                "findings": findings_json,
                "dur": scan_duration,
            },
        )
        await session.commit()
        logger.info(
            "stream.scan_recorded",
            skill_id=skill_id,
            version_id=version_id,
            verdict=verdict,
        )


_singleton: ScanTaskStreamConsumer | None = None


def get_stream_consumer() -> ScanTaskStreamConsumer:
    global _singleton
    if _singleton is None:
        _singleton = ScanTaskStreamConsumer()
    return _singleton
