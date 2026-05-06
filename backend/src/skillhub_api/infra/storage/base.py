"""Object storage abstraction.

Ports ``ObjectStorageService.java`` into Python. Two implementations exist:
``LocalFileStorage`` (dev / tests) and ``S3Storage`` (prod, MinIO-compatible
via ``aioboto3``). Method names mirror the Java service so future readers
who know the Spring codebase navigate easily.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import timedelta
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ObjectMetadata:
    key: str
    size: int
    content_type: str | None


class ObjectStorage(Protocol):
    async def put_object(
        self,
        key: str,
        data: bytes,
        *,
        content_type: str | None = None,
    ) -> None: ...

    async def get_object(self, key: str) -> bytes: ...

    async def iter_object(self, key: str) -> AsyncIterator[bytes]: ...

    async def delete_object(self, key: str) -> None: ...

    async def delete_objects(self, keys: list[str]) -> None: ...

    async def exists(self, key: str) -> bool: ...

    async def metadata(self, key: str) -> ObjectMetadata | None: ...

    async def presigned_url(
        self,
        key: str,
        expiry: timedelta,
        *,
        download_filename: str | None = None,
    ) -> str: ...
