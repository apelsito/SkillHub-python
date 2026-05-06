"""S3 (MinIO-compatible) object storage via aioboto3.

Env-var configuration mirrors the Java ``S3StorageProperties`` so existing
deployments can reuse their secret stores unchanged.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import timedelta
from typing import Any

import aioboto3
from botocore.exceptions import ClientError

from skillhub_api.errors import NotFoundError
from skillhub_api.infra.storage.base import ObjectMetadata
from skillhub_api.settings import StorageSettings


class S3Storage:
    def __init__(self, settings: StorageSettings) -> None:
        self._s = settings
        self._session = aioboto3.Session()

    def _client_kwargs(self) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "service_name": "s3",
            "aws_access_key_id": self._s.s3_access_key.get_secret_value() or None,
            "aws_secret_access_key": self._s.s3_secret_key.get_secret_value() or None,
            "region_name": self._s.s3_region,
        }
        if self._s.s3_endpoint:
            kwargs["endpoint_url"] = self._s.s3_endpoint
        return kwargs

    def _client(self):
        return self._session.client(**self._client_kwargs())

    async def ensure_bucket(self) -> None:
        """Create the bucket if missing and auto-create is enabled."""
        if not self._s.s3_auto_create_bucket:
            return
        async with self._client() as c:
            try:
                await c.head_bucket(Bucket=self._s.s3_bucket)
            except ClientError:
                await c.create_bucket(Bucket=self._s.s3_bucket)

    async def put_object(
        self,
        key: str,
        data: bytes,
        *,
        content_type: str | None = None,
    ) -> None:
        extra: dict[str, Any] = {}
        if content_type:
            extra["ContentType"] = content_type
        async with self._client() as c:
            await c.put_object(Bucket=self._s.s3_bucket, Key=key, Body=data, **extra)

    async def get_object(self, key: str) -> bytes:
        async with self._client() as c:
            try:
                resp = await c.get_object(Bucket=self._s.s3_bucket, Key=key)
            except ClientError as exc:
                if exc.response.get("Error", {}).get("Code") in {"NoSuchKey", "404"}:
                    raise NotFoundError("STORAGE_KEY_NOT_FOUND", f"missing object: {key}") from exc
                raise
            body = await resp["Body"].read()
            return body

    async def iter_object(self, key: str) -> AsyncIterator[bytes]:
        async with self._client() as c:
            resp = await c.get_object(Bucket=self._s.s3_bucket, Key=key)
            stream = resp["Body"]
            while True:
                chunk = await stream.read(64 * 1024)
                if not chunk:
                    return
                yield chunk

    async def delete_object(self, key: str) -> None:
        async with self._client() as c:
            await c.delete_object(Bucket=self._s.s3_bucket, Key=key)

    async def delete_objects(self, keys: list[str]) -> None:
        if not keys:
            return
        async with self._client() as c:
            await c.delete_objects(
                Bucket=self._s.s3_bucket,
                Delete={"Objects": [{"Key": k} for k in keys]},
            )

    async def exists(self, key: str) -> bool:
        async with self._client() as c:
            try:
                await c.head_object(Bucket=self._s.s3_bucket, Key=key)
                return True
            except ClientError:
                return False

    async def metadata(self, key: str) -> ObjectMetadata | None:
        async with self._client() as c:
            try:
                resp = await c.head_object(Bucket=self._s.s3_bucket, Key=key)
            except ClientError:
                return None
            return ObjectMetadata(
                key=key,
                size=int(resp.get("ContentLength", 0)),
                content_type=resp.get("ContentType"),
            )

    async def presigned_url(
        self,
        key: str,
        expiry: timedelta,
        *,
        download_filename: str | None = None,
    ) -> str:
        params: dict[str, Any] = {"Bucket": self._s.s3_bucket, "Key": key}
        if download_filename:
            params["ResponseContentDisposition"] = f'attachment; filename="{download_filename}"'
        async with self._client() as c:
            return await c.generate_presigned_url(
                ClientMethod="get_object",
                Params=params,
                ExpiresIn=int(expiry.total_seconds()),
            )
