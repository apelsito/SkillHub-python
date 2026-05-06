"""Async engine + session factory."""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from skillhub_api.settings import get_settings

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _normalize_asyncpg_url(url: str) -> str:
    # Accept both `postgresql://` and `postgresql+asyncpg://`. The env default
    # uses the asyncpg form; older deployments may pass plain `postgresql://`.
    if url.startswith("postgresql+asyncpg://") or url.startswith("postgresql+psycopg://"):
        return url
    if url.startswith("postgresql://"):
        return "postgresql+asyncpg://" + url[len("postgresql://") :]
    if url.startswith("jdbc:postgresql://"):
        # Spring-style JDBC URL — strip the jdbc: prefix and swap scheme.
        return "postgresql+asyncpg://" + url[len("jdbc:postgresql://") :]
    return url


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        settings = get_settings()
        url = _normalize_asyncpg_url(settings.db.url)
        _engine = create_async_engine(
            url,
            pool_pre_ping=True,
            pool_size=settings.db.pool_max_size,
            max_overflow=0,
            future=True,
        )
    return _engine


def _session_maker() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(),
            expire_on_commit=False,
            autoflush=False,
        )
    return _session_factory


AsyncSessionLocal = _session_maker


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding an `AsyncSession`."""
    async with _session_maker()() as session:
        yield session


async def dispose_engine() -> None:
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None
