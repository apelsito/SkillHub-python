"""End-to-end: star/rate/subscribe flows + notification pipeline.

The Redis bridge is started at lifespan but will silently fail in tests
without a Redis container — that's fine, the in-memory queue still
receives local publishes, which is all these tests exercise.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from skillhub_api.events.bus import reset_event_bus
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
        json={"username": username, "password": "password123", "email": f"{username}@x.com"},
    )
    assert r.status_code == 200, r.text
    return _data(r)["userId"]


async def _publish_private(client: AsyncClient, name: str) -> int:
    zip_bytes = _zip(
        {
            "SKILL.md": f"---\nname: {name}\ndescription: d\nversion: 1.0.0\n---\n".encode(),
            "a.py": b"pass",
        }
    )
    r = await client.post(
        "/api/v1/skills/global/publish",
        files={"file": ("pkg.zip", zip_bytes, "application/zip")},
        data={"visibility": "PRIVATE"},
    )
    assert r.status_code == 201, r.text
    return _data(r)["skillId"]


async def test_star_roundtrip_and_count_rollup(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    await _register(async_client, "star_owner")
    skill_id = await _publish_private(async_client, "Starry")

    r = await async_client.put(f"/api/v1/skills/{skill_id}/star")
    assert r.status_code == 200 and _data(r)["value"] is True

    # Status reflects the star.
    status = await async_client.get(f"/api/v1/skills/{skill_id}/star")
    assert _data(status)["value"] is True

    # Listener should have rolled up the count. Re-query the detail.
    await db_session.rollback()
    detail = await async_client.get("/api/v1/skills/global/starry")
    assert _data(detail)["starCount"] == 1

    # Unstar flips everything back.
    r = await async_client.delete(f"/api/v1/skills/{skill_id}/star")
    assert r.status_code == 200
    await db_session.rollback()
    detail = await async_client.get("/api/v1/skills/global/starry")
    assert _data(detail)["starCount"] == 0


async def test_rating_rollup_updates_avg_and_count(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    await _register(async_client, "rate_owner")
    skill_id = await _publish_private(async_client, "Ratable")

    r = await async_client.put(f"/api/v1/skills/{skill_id}/rating", json={"score": 5})
    assert r.status_code == 200 and _data(r)["score"] == 5
    await db_session.rollback()
    detail = await async_client.get("/api/v1/skills/global/ratable")
    assert _data(detail)["ratingCount"] == 1
    assert float(_data(detail)["ratingAvg"]) == pytest.approx(5.0)

    # Updating the same user's score is an upsert, not an insert.
    await async_client.put(f"/api/v1/skills/{skill_id}/rating", json={"score": 3})
    await db_session.rollback()
    detail = await async_client.get("/api/v1/skills/global/ratable")
    assert _data(detail)["ratingCount"] == 1
    assert float(_data(detail)["ratingAvg"]) == pytest.approx(3.0)


async def test_subscription_creates_notification_for_subscriber(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    # Owner publishes once.
    owner_id = await _register(async_client, "sub_owner")
    skill_id = await _publish_private(async_client, "Subbed Skill")

    # Second user subscribes in their own session.
    sub_client = AsyncClient(
        transport=async_client._transport,  # type: ignore[attr-defined]
        base_url="http://testserver",
    )
    try:
        sub_user = await _register(sub_client, "sub_user")
        r = await sub_client.put(f"/api/v1/skills/{skill_id}/subscription")
        assert r.status_code == 200 and _data(r)["value"] is True
    finally:
        await sub_client.aclose()

    # Owner publishes a new version — the subscriber should get a notification.
    zip_bytes = _zip(
        {
            "SKILL.md": b"---\nname: Subbed Skill\ndescription: d\nversion: 2.0.0\n---\n",
            "a.py": b"pass",
        }
    )
    r = await async_client.post(
        "/api/v1/skills/global/publish",
        files={"file": ("pkg.zip", zip_bytes, "application/zip")},
        data={"visibility": "PRIVATE"},
    )
    assert r.status_code == 201

    await db_session.rollback()
    count = (
        await db_session.execute(
            text(
                "SELECT COUNT(*) FROM notification WHERE recipient_id = :u "
                "AND event_type = 'SUBSCRIPTION_NEW_VERSION'"
            ),
            {"u": sub_user},
        )
    ).scalar_one()
    assert int(count) == 1

    # Publisher still gets their own SKILL_PUBLISHED notification (once per publish).
    own_count = (
        await db_session.execute(
            text(
                "SELECT COUNT(*) FROM notification WHERE recipient_id = :u "
                "AND event_type = 'SKILL_PUBLISHED'"
            ),
            {"u": owner_id},
        )
    ).scalar_one()
    assert int(own_count) >= 1


async def test_notification_list_and_mark_read(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    await _register(async_client, "notif_user")
    await _publish_private(async_client, "Notif Skill")

    # List returns at least the auto-generated publish notification.
    listing = await async_client.get("/api/v1/notifications")
    assert listing.status_code == 200
    body = _data(listing)
    assert body["total"] >= 1
    notif_id = body["items"][0]["id"]

    # Unread count reflects the same row.
    unread = await async_client.get("/api/v1/notifications/unread-count")
    assert _data(unread)["count"] >= 1

    # Mark one as read; unread count decreases by 1.
    await async_client.put(f"/api/v1/notifications/{notif_id}/read")
    unread_after = await async_client.get("/api/v1/notifications/unread-count")
    assert _data(unread_after)["count"] == _data(unread)["count"] - 1


async def test_preferences_default_to_enabled(async_client: AsyncClient) -> None:
    await _register(async_client, "pref_user")
    r = await async_client.get("/api/v1/notification-preferences")
    assert r.status_code == 200
    prefs = _data(r)
    assert len(prefs) == 4
    assert all(p["enabled"] for p in prefs)


async def test_preferences_update_roundtrips(async_client: AsyncClient) -> None:
    await _register(async_client, "pref_user_2")
    r = await async_client.put(
        "/api/v1/notification-preferences",
        json={
            "preferences": [
                {"category": "PUBLISH", "channel": "IN_APP", "enabled": False},
            ]
        },
    )
    assert r.status_code == 200
    prefs = {(p["category"], p["channel"]): p["enabled"] for p in _data(r)}
    assert prefs[("PUBLISH", "IN_APP")] is False
    # Untouched categories remain enabled by default.
    assert prefs[("REVIEW", "IN_APP")] is True
