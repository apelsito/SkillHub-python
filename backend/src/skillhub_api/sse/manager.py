"""Per-user SSE stream manager.

In-memory fan-out (one asyncio.Queue per open connection) plus a Redis
pub/sub bridge so a notification written on pod A reaches the SSE
connection on pod B. Both layers are optional: if Redis is unreachable
we keep serving in-process subscribers and log the error.

Connection limits mirror the Java ``SseEmitterManager``:
  * 5 concurrent connections per user
  * 1000 total connections per process
  * 10-minute connection timeout
  * 30-second heartbeat
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from skillhub_api.logging import get_logger

logger = get_logger(__name__)

MAX_PER_USER = 5
MAX_TOTAL = 1000
CONNECTION_TIMEOUT_SECONDS = 600.0
HEARTBEAT_SECONDS = 30.0
REDIS_CHANNEL = "skillhub:notifications"


@dataclass(slots=True)
class _Connection:
    user_id: str
    queue: asyncio.Queue[str]
    opened_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class NotificationStreamManager:
    def __init__(self) -> None:
        self._by_user: dict[str, list[_Connection]] = {}
        self._lock = asyncio.Lock()
        self._redis_task: asyncio.Task | None = None

    async def connect(self, user_id: str) -> _Connection:
        async with self._lock:
            user_conns = self._by_user.setdefault(user_id, [])
            # Evict the oldest when the user is over their per-user limit.
            while len(user_conns) >= MAX_PER_USER:
                oldest = user_conns.pop(0)
                with suppress(Exception):
                    oldest.queue.put_nowait("__closed__")
            total = sum(len(v) for v in self._by_user.values())
            if total >= MAX_TOTAL:
                raise RuntimeError("SSE connection limit reached")
            conn = _Connection(user_id=user_id, queue=asyncio.Queue(maxsize=64))
            user_conns.append(conn)
            return conn

    async def disconnect(self, conn: _Connection) -> None:
        async with self._lock:
            user_conns = self._by_user.get(conn.user_id, [])
            if conn in user_conns:
                user_conns.remove(conn)
            if not user_conns:
                self._by_user.pop(conn.user_id, None)

    async def publish(self, *, recipient_id: str, payload: dict[str, Any]) -> None:
        """Fan out a notification to every open connection for the user.

        Local delivery only — cross-pod delivery is handled by the Redis
        bridge task subscribing to ``REDIS_CHANNEL``.
        """
        async with self._lock:
            conns = list(self._by_user.get(recipient_id, ()))
        data = json.dumps(payload)
        for conn in conns:
            if conn.queue.full():
                with suppress(asyncio.QueueEmpty):
                    conn.queue.get_nowait()  # drop oldest if slow consumer
            with suppress(Exception):
                conn.queue.put_nowait(data)

    async def stream(self, conn: _Connection) -> AsyncIterator[dict[str, str]]:
        yield {"event": "connected", "data": "ok"}
        last_heartbeat = asyncio.get_event_loop().time()
        started = last_heartbeat
        while True:
            timeout = HEARTBEAT_SECONDS - (asyncio.get_event_loop().time() - last_heartbeat)
            if timeout <= 0:
                yield {"event": "heartbeat", "data": "ping"}
                last_heartbeat = asyncio.get_event_loop().time()
                continue
            try:
                msg = await asyncio.wait_for(conn.queue.get(), timeout=timeout)
            except TimeoutError:
                yield {"event": "heartbeat", "data": "ping"}
                last_heartbeat = asyncio.get_event_loop().time()
                continue

            if msg == "__closed__":
                return

            yield {"event": "notification", "data": msg}
            # Enforce absolute connection timeout.
            if asyncio.get_event_loop().time() - started >= CONNECTION_TIMEOUT_SECONDS:
                return

    async def start_redis_bridge(self) -> None:
        """Subscribe to the cross-pod channel and relay messages locally.

        Runs until cancelled at shutdown. Failures (no Redis available
        in dev, transient disconnects) are logged and retried after a
        short backoff.
        """
        if self._redis_task is not None:
            return

        async def _runner() -> None:
            from skillhub_api.infra.redis_client import get_redis

            while True:
                try:
                    redis = get_redis()
                    pubsub = redis.pubsub()
                    await pubsub.subscribe(REDIS_CHANNEL)
                    async for message in pubsub.listen():
                        if message.get("type") != "message":
                            continue
                        raw = message.get("data")
                        if not raw:
                            continue
                        try:
                            envelope = json.loads(raw)
                        except json.JSONDecodeError:
                            continue
                        recipient_id = envelope.get("recipient_id")
                        payload = envelope.get("payload")
                        if isinstance(recipient_id, str) and isinstance(payload, dict):
                            await self.publish(recipient_id=recipient_id, payload=payload)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:  # pragma: no cover - infra failure
                    logger.warning("sse.redis_bridge_retry", error=str(exc))
                    await asyncio.sleep(2.0)

        self._redis_task = asyncio.create_task(_runner(), name="sse-redis-bridge")

    async def stop_redis_bridge(self) -> None:
        task = self._redis_task
        if task is None:
            return
        task.cancel()
        with suppress(asyncio.CancelledError, Exception):
            await task
        self._redis_task = None


_singleton: NotificationStreamManager | None = None


def get_stream_manager() -> NotificationStreamManager:
    global _singleton
    if _singleton is None:
        _singleton = NotificationStreamManager()
    return _singleton


async def redis_broadcast(*, recipient_id: str, payload: dict[str, Any]) -> None:
    """Publish a notification envelope on the cross-pod Redis channel.

    Called by the notification listener so every pod's manager can fan it
    out to its own SSE subscribers. Safe to fail silently — the
    notification row is already persisted and the /list endpoint still
    shows it on next poll.
    """
    try:
        from skillhub_api.infra.redis_client import get_redis

        redis = get_redis()
        envelope = json.dumps({"recipient_id": recipient_id, "payload": payload})
        await redis.publish(REDIS_CHANNEL, envelope)
    except Exception as exc:  # pragma: no cover - infra failure
        logger.warning("sse.redis_publish_failed", error=str(exc))
