"""Async Redis client singleton.

One connection pool per process, reused across routers. Closed during the
FastAPI lifespan shutdown path.
"""

from __future__ import annotations

from redis.asyncio import Redis, from_url

from skillhub_api.settings import get_settings

_client: Redis | None = None


def _build_url() -> str:
    settings = get_settings()
    host = settings.redis.host
    port = settings.redis.port
    password = settings.redis.password.get_secret_value()
    if password:
        return f"redis://:{password}@{host}:{port}/0"
    return f"redis://{host}:{port}/0"


def get_redis() -> Redis:
    global _client
    if _client is None:
        _client = from_url(_build_url(), encoding="utf-8", decode_responses=True)
    return _client


async def close_redis() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
