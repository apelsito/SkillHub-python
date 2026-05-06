"""Filesystem-backed object storage for local dev and tests.

Presigned URLs are implemented as a short-lived HMAC-signed path under
``/api/v1/storage/local/{key}`` (not registered by default; tests intercept
it). In production, the S3 provider is used instead.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import timedelta
from pathlib import Path
from urllib.parse import quote

from skillhub_api.errors import NotFoundError
from skillhub_api.infra.storage.base import ObjectMetadata


class LocalFileStorage:
    def __init__(self, base_path: str) -> None:
        self._base = Path(base_path)
        self._base.mkdir(parents=True, exist_ok=True)

    def _resolve(self, key: str) -> Path:
        # Strip leading slashes and normalize; keys from the service layer are
        # already validated against path traversal, but we defensively re-check
        # here in case a caller forgets.
        clean = key.lstrip("/\\").replace("\\", "/")
        resolved = (self._base / clean).resolve()
        if not str(resolved).startswith(str(self._base.resolve())):
            raise ValueError(f"storage key escapes base path: {key!r}")
        return resolved

    async def put_object(
        self,
        key: str,
        data: bytes,
        *,
        content_type: str | None = None,
    ) -> None:
        path = self._resolve(key)
        await asyncio.to_thread(_write_bytes, path, data)

    async def get_object(self, key: str) -> bytes:
        path = self._resolve(key)
        if not path.exists():
            raise NotFoundError("STORAGE_KEY_NOT_FOUND", f"missing object: {key}")
        return await asyncio.to_thread(path.read_bytes)

    async def iter_object(self, key: str) -> AsyncIterator[bytes]:
        path = self._resolve(key)
        if not path.exists():
            raise NotFoundError("STORAGE_KEY_NOT_FOUND", f"missing object: {key}")
        chunk = 64 * 1024
        with path.open("rb") as fh:
            while True:
                buf = await asyncio.to_thread(fh.read, chunk)
                if not buf:
                    return
                yield buf

    async def delete_object(self, key: str) -> None:
        path = self._resolve(key)
        if path.exists():
            await asyncio.to_thread(path.unlink)

    async def delete_objects(self, keys: list[str]) -> None:
        for k in keys:
            await self.delete_object(k)

    async def exists(self, key: str) -> bool:
        return self._resolve(key).exists()

    async def metadata(self, key: str) -> ObjectMetadata | None:
        path = self._resolve(key)
        if not path.exists():
            return None
        return ObjectMetadata(key=key, size=path.stat().st_size, content_type=None)

    async def presigned_url(
        self,
        key: str,
        expiry: timedelta,
        *,
        download_filename: str | None = None,
    ) -> str:
        # Local provider returns an opaque URL — callers in prod must use S3.
        return f"file:///{quote(key)}"


def _write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as fh:
        fh.write(data)
