import asyncio
from pathlib import Path

import pytest

from skillhub_api.errors import NotFoundError
from skillhub_api.infra.storage.local import LocalFileStorage


@pytest.fixture
def storage(tmp_path: Path) -> LocalFileStorage:
    return LocalFileStorage(str(tmp_path))


async def test_put_get_roundtrip(storage: LocalFileStorage) -> None:
    await storage.put_object("a/b.txt", b"hello", content_type="text/plain")
    assert await storage.exists("a/b.txt")
    assert await storage.get_object("a/b.txt") == b"hello"


async def test_missing_key_raises(storage: LocalFileStorage) -> None:
    with pytest.raises(NotFoundError):
        await storage.get_object("nope")


async def test_delete_object(storage: LocalFileStorage) -> None:
    await storage.put_object("x", b"data")
    await storage.delete_object("x")
    assert not await storage.exists("x")


async def test_rejects_traversal(storage: LocalFileStorage) -> None:
    with pytest.raises(ValueError, match="escapes"):
        await storage.put_object("../escape", b"x")


async def test_iter_object_streams(storage: LocalFileStorage) -> None:
    await storage.put_object("big.txt", b"X" * 150_000)
    chunks: list[bytes] = []
    async for chunk in storage.iter_object("big.txt"):
        chunks.append(chunk)
    assert b"".join(chunks) == b"X" * 150_000


async def test_metadata_returns_size(storage: LocalFileStorage) -> None:
    await storage.put_object("m", b"abcd")
    md = await storage.metadata("m")
    assert md is not None
    assert md.size == 4


async def test_exists_false_for_missing(storage: LocalFileStorage) -> None:
    assert not await storage.exists("missing")
    # ensure ``asyncio`` is imported and used (guards against rename regressions)
    assert asyncio.iscoroutinefunction(storage.get_object)
