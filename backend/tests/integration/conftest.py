"""Integration test fixtures backed by testcontainers-postgres.

These tests spin up a real Postgres 16 image per session and run the Alembic
migrations against it. Function-scoped transactions keep each test isolated.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from sqlalchemy.pool import NullPool
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer

from skillhub_api.infra.db.session import dispose_engine
from skillhub_api.settings import get_settings


@pytest.fixture(scope="session")
def postgres_container() -> Iterator[PostgresContainer]:
    container = PostgresContainer("postgres:16-alpine")
    with container as pg:
        yield pg


@pytest.fixture(scope="session")
def database_url(postgres_container: PostgresContainer) -> str:
    # testcontainers returns a psycopg2-style URL; rewrite for asyncpg.
    raw = postgres_container.get_connection_url()
    if raw.startswith("postgresql+psycopg2://"):
        raw = "postgresql+asyncpg://" + raw[len("postgresql+psycopg2://") :]
    elif raw.startswith("postgresql://"):
        raw = "postgresql+asyncpg://" + raw[len("postgresql://") :]
    return raw


@pytest.fixture(scope="session", autouse=True)
def _apply_migrations(database_url: str) -> Iterator[None]:
    os.environ["SPRING_DATASOURCE_URL"] = database_url
    get_settings.cache_clear()
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(cfg, "head")
    yield


@pytest_asyncio.fixture(scope="session")
async def _engine(database_url: str):
    engine = create_async_engine(database_url, future=True, poolclass=NullPool)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def _dispose_app_engine_after_test() -> AsyncIterator[None]:
    yield
    await dispose_engine()


@pytest_asyncio.fixture
async def db_session(_engine) -> AsyncIterator[AsyncSession]:
    """Function-scoped session wrapped in a savepoint rolled back at teardown."""
    async with _engine.connect() as conn:
        trans = await conn.begin()
        factory = async_sessionmaker(bind=conn, expire_on_commit=False, autoflush=False)
        async with factory() as session:
            try:
                yield session
            finally:
                await trans.rollback()
