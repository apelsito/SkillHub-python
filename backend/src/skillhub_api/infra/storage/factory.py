"""Return the configured storage backend.

Caller-scoped singleton: one ``S3Storage`` or ``LocalFileStorage`` instance
per process. Resolved lazily so unit tests that don't need storage don't pay
the aioboto3 import cost.
"""

from __future__ import annotations

from functools import lru_cache

from skillhub_api.infra.storage.base import ObjectStorage
from skillhub_api.infra.storage.local import LocalFileStorage
from skillhub_api.infra.storage.s3 import S3Storage
from skillhub_api.settings import get_settings


@lru_cache(maxsize=1)
def get_storage() -> ObjectStorage:
    settings = get_settings()
    if settings.storage.provider == "s3":
        return S3Storage(settings.storage)
    if settings.storage.provider == "local":
        return LocalFileStorage(settings.storage.local_base_path)
    raise ValueError(f"unknown storage provider: {settings.storage.provider!r}")
