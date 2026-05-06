"""Publish → list → get → download end-to-end against real Postgres.

Uses the LocalFileStorage under a temp directory so the test doesn't need
MinIO. S3-specific behavior (presigned URLs) is exercised separately in
contract tests when MinIO is available.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from skillhub_api.infra.storage import get_storage
from skillhub_api.infra.storage.local import LocalFileStorage
from skillhub_api.main import create_app

pytestmark = pytest.mark.integration


def _data(response) -> dict | list:
    return response.json()["data"]


def _build_zip(entries: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return buf.getvalue()


@pytest.fixture
def app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    # Force local storage under tmp_path for this test.
    monkeypatch.setenv("SKILLHUB_STORAGE_PROVIDER", "local")
    monkeypatch.setenv("STORAGE_BASE_PATH", str(tmp_path / "storage"))
    from skillhub_api.settings import get_settings

    get_settings.cache_clear()
    get_storage.cache_clear()
    return create_app()


@pytest.fixture
async def async_client(app: FastAPI) -> AsyncClient:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as c:
        yield c


async def _register(client: AsyncClient, username: str) -> None:
    r = await client.post(
        "/api/v1/auth/local/register",
        json={"username": username, "password": "publishpass1", "email": f"{username}@x.com"},
    )
    assert r.status_code == 200, r.text


async def test_publish_private_then_download(async_client: AsyncClient) -> None:
    await _register(async_client, "publish_user_1")
    zip_bytes = _build_zip(
        {
            "SKILL.md": (
                b"---\nname: My Python Skill\ndescription: A port test\nversion: 1.0.0\n---\nbody"
            ),
            "src/main.py": b"print('hello')",
            "README.md": b"# hello",
        }
    )
    resp = await async_client.post(
        "/api/v1/skills/global/publish",
        files={"file": ("pkg.zip", zip_bytes, "application/zip")},
        data={"visibility": "PRIVATE"},
    )
    assert resp.status_code == 201, resp.text
    payload = _data(resp)
    assert payload["slug"] == "my-python-skill"
    assert payload["version"] == "1.0.0"
    assert payload["status"] == "PUBLISHED"
    assert payload["fileCount"] == 3

    # List shows the new skill.
    listing = await async_client.get("/api/v1/skills", params={"namespace": "global"})
    assert listing.status_code == 200
    ids = [s["id"] for s in _data(listing)["items"]]
    assert payload["skillId"] in ids

    # Detail roundtrip.
    detail = await async_client.get("/api/v1/skills/global/my-python-skill")
    assert detail.status_code == 200
    assert _data(detail)["latestVersionId"] is not None

    # Version + files listings work.
    versions = await async_client.get("/api/v1/skills/global/my-python-skill/versions")
    assert versions.status_code == 200
    assert _data(versions)["total"] == 1

    files = await async_client.get("/api/v1/skills/global/my-python-skill/versions/1.0.0/files")
    assert files.status_code == 200
    paths = {f["filePath"] for f in _data(files)}
    assert {"SKILL.md", "src/main.py", "README.md"} == paths

    # Download returns the bundle (local mode = streamed).
    dl = await async_client.get("/api/v1/skills/global/my-python-skill/download")
    assert dl.status_code == 200
    assert dl.headers["content-type"].startswith("application/zip")

    # Download counter incremented.
    after = await async_client.get("/api/v1/skills/global/my-python-skill")
    assert _data(after)["downloadCount"] == 1


async def test_publish_public_lands_in_pending_review(async_client: AsyncClient) -> None:
    await _register(async_client, "publish_user_2")
    zip_bytes = _build_zip(
        {
            "SKILL.md": (b"---\nname: Public Skill\ndescription: d\nversion: 0.1.0\n---\nbody"),
            "main.py": b"pass",
        }
    )
    resp = await async_client.post(
        "/api/v1/skills/global/publish",
        files={"file": ("pkg.zip", zip_bytes, "application/zip")},
        data={"visibility": "PUBLIC"},
    )
    assert resp.status_code == 201, resp.text
    assert _data(resp)["status"] == "PENDING_REVIEW"


async def test_archive_and_unarchive(async_client: AsyncClient) -> None:
    await _register(async_client, "publish_user_3")
    zip_bytes = _build_zip(
        {
            "SKILL.md": b"---\nname: Archive Me\ndescription: d\nversion: 0.0.1\n---\n",
            "a.py": b"pass",
        }
    )
    await async_client.post(
        "/api/v1/skills/global/publish",
        files={"file": ("pkg.zip", zip_bytes, "application/zip")},
        data={"visibility": "PRIVATE"},
    )
    a = await async_client.post("/api/v1/skills/global/archive-me/archive")
    assert a.status_code == 200
    assert _data(a)["status"] == "ARCHIVED"

    u = await async_client.post("/api/v1/skills/global/archive-me/unarchive")
    assert u.status_code == 200
    assert _data(u)["status"] == "ACTIVE"


async def test_invalid_zip_is_400(async_client: AsyncClient) -> None:
    await _register(async_client, "publish_user_4")
    r = await async_client.post(
        "/api/v1/skills/global/publish",
        files={"file": ("bad.zip", b"not a zip", "application/zip")},
        data={"visibility": "PRIVATE"},
    )
    assert r.status_code == 400
    assert r.json()["errorCode"] == "INVALID_ZIP"


async def test_storage_cleanup(tmp_path: Path) -> None:
    # Sanity: LocalFileStorage round-trip in isolation.
    s = LocalFileStorage(str(tmp_path / "iso"))
    await s.put_object("k", b"v")
    assert await s.get_object("k") == b"v"
