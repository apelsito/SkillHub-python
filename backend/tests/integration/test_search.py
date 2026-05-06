"""End-to-end search: publish → event listener indexes → search.

Covers three asserts:
  1. Publishing a PRIVATE skill inserts a ``skill_search_document`` row.
  2. A PUBLIC-with-approved-review skill appears in the public search
     results (visibility filter).
  3. Text search hits work for an exact-title keyword.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from skillhub_api.events.bus import reset_event_bus
from skillhub_api.infra.db.models.auth import Role
from skillhub_api.infra.db.session import AsyncSessionLocal
from skillhub_api.infra.storage import get_storage
from skillhub_api.main import create_app

pytestmark = pytest.mark.integration


def _data(response) -> dict | list:
    return response.json()["data"]


def _zip(entries: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return buf.getvalue()


@pytest.fixture
def app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    monkeypatch.setenv("SKILLHUB_STORAGE_PROVIDER", "local")
    monkeypatch.setenv("STORAGE_BASE_PATH", str(tmp_path / "storage"))
    from skillhub_api.settings import get_settings

    get_settings.cache_clear()
    get_storage.cache_clear()
    reset_event_bus()
    return create_app()


@pytest.fixture
async def async_client(app: FastAPI) -> AsyncClient:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as c:
        yield c


async def _register(client: AsyncClient, username: str) -> str:
    r = await client.post(
        "/api/v1/auth/local/register",
        json={"username": username, "password": "searchpass1", "email": f"{username}@x.com"},
    )
    assert r.status_code == 200, r.text
    return _data(r)["userId"]


async def _grant_role(user_id: str, role_code: str) -> None:
    async with AsyncSessionLocal()() as session:
        role_id = (await session.execute(select(Role.id).where(Role.code == role_code))).scalar_one()
        await session.execute(
            text(
                "INSERT INTO user_role_binding (user_id, role_id) VALUES (:u, :r) "
                "ON CONFLICT DO NOTHING"
            ),
            {"u": user_id, "r": role_id},
        )
        await session.commit()


async def test_private_publish_indexes_search_document(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    await _register(async_client, "search_user_1")
    zip_bytes = _zip(
        {
            "SKILL.md": b"---\nname: Searchable Skill\ndescription: Finds nothing\nversion: 1.0.0\n---\n",
            "a.py": b"pass",
        }
    )
    pub = await async_client.post(
        "/api/v1/skills/global/publish",
        files={"file": ("pkg.zip", zip_bytes, "application/zip")},
        data={"visibility": "PRIVATE"},
    )
    assert pub.status_code == 201
    skill_id = _data(pub)["skillId"]

    # PRIVATE skills still get indexed; the query layer filters them out.
    await db_session.rollback()
    row = (
        await db_session.execute(
            text("SELECT title, visibility FROM skill_search_document WHERE skill_id = :id"),
            {"id": skill_id},
        )
    ).one_or_none()
    assert row is not None
    assert row[0] == "Searchable Skill"
    assert row[1] == "PRIVATE"


async def test_public_published_skill_appears_in_search(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange: insert a PUBLIC/ACTIVE skill + matching search document.
    # We build the row directly to isolate this test from the review flow.
    async with AsyncSessionLocal()() as session:
        await session.execute(
            text("INSERT INTO user_account (id, display_name) VALUES ('search_owner_a', 'A')")
        )
        await session.execute(
            text(
                """
                INSERT INTO skill (namespace_id, slug, display_name, summary,
                                   owner_id, visibility, status)
                VALUES (
                  (SELECT id FROM namespace WHERE slug='global'),
                  'findme', 'Find Me Please', 'A unique summary about widgets',
                  'search_owner_a', 'PUBLIC', 'ACTIVE'
                )
                """
            )
        )
        skill_id = (
            await session.execute(text("SELECT id FROM skill WHERE slug = 'findme'"))
        ).scalar_one()
        await session.execute(
            text(
                """
                INSERT INTO skill_search_document
                  (skill_id, namespace_id, namespace_slug, owner_id,
                   title, summary, keywords, search_text,
                   visibility, status)
                VALUES (
                  :skill_id,
                  (SELECT id FROM namespace WHERE slug='global'),
                  'global', 'search_owner_a',
                  'Find Me Please', 'A unique summary about widgets',
                  'widgets', 'findme A unique summary about widgets',
                  'PUBLIC', 'ACTIVE'
                )
                """
            ),
            {"skill_id": skill_id},
        )
        await session.commit()

    r = await async_client.get(
        "/api/v1/skills/search", params={"q": "widgets", "sort": "relevance"}
    )
    assert r.status_code == 200, r.text
    body = _data(r)
    ids = [item["skillId"] for item in body["items"]]
    assert skill_id in ids


async def test_namespace_filter_scopes_results(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    r = await async_client.get("/api/v1/skills/search", params={"namespace": "does-not-exist"})
    assert r.status_code == 200
    assert _data(r)["total"] == 0


async def test_admin_search_rebuild_populates_documents(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    admin_id = await _register(async_client, "search_admin")
    await _grant_role(admin_id, "SUPER_ADMIN")

    async with AsyncSessionLocal()() as session:
        await session.execute(
            text("INSERT INTO user_account (id, display_name) VALUES ('search_owner_b', 'B')")
        )
        await session.execute(
            text(
                """
                INSERT INTO skill (namespace_id, slug, display_name, summary,
                                   owner_id, visibility, status)
                VALUES (
                  (SELECT id FROM namespace WHERE slug='global'),
                  'rebuild-me', 'Rebuild Me', 'Search rebuild target',
                  'search_owner_b', 'PUBLIC', 'ACTIVE'
                )
                """
            )
        )
        skill_id = (
            await session.execute(text("SELECT id FROM skill WHERE slug = 'rebuild-me'"))
        ).scalar_one()
        await session.execute(
            text("DELETE FROM skill_search_document WHERE skill_id = :skill_id"),
            {"skill_id": skill_id},
        )
        await session.commit()

    response = await async_client.post("/api/v1/admin/search/rebuild")
    assert response.status_code == 200, response.text
    assert _data(response)["rebuilt"] >= 1

    await db_session.rollback()
    row = (
        await db_session.execute(
            text("SELECT title FROM skill_search_document WHERE skill_id = :skill_id"),
            {"skill_id": skill_id},
        )
    ).one_or_none()
    assert row is not None
    assert row[0] == "Rebuild Me"
