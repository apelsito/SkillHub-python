"""End-to-end governance flows: publish PUBLIC → review → approve, and
submit-report → audit-log audit trail.

The tests exercise the event bus (audit listener writes to audit_log
post-commit) so they also cover that pipe indirectly.
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
from skillhub_api.infra.db.session import AsyncSessionLocal
from skillhub_api.infra.db.models.auth import Role
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


async def _grant_role(db: AsyncSession, user_id: str, role_code: str) -> None:
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


async def test_report_flow_writes_audit_log(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    # Arrange: owner publishes a skill.
    await _register(async_client, "report_owner")
    zip_bytes = _zip(
        {
            "SKILL.md": b"---\nname: Reported Skill\ndescription: d\nversion: 1.0.0\n---\n",
            "a.py": b"pass",
        }
    )
    pub = await async_client.post(
        "/api/v1/skills/global/publish",
        files={"file": ("pkg.zip", zip_bytes, "application/zip")},
        data={"visibility": "PRIVATE"},
    )
    assert pub.status_code == 201, pub.text
    skill_id = _data(pub)["skillId"]

    # Act: another user reports the skill.
    reporter_client = AsyncClient(
        transport=async_client._transport,
        base_url="http://testserver",  # type: ignore[attr-defined]
    )
    try:
        reporter_id = await _register(reporter_client, "reporter_user")
        r = await reporter_client.post(
            f"/api/v1/skills/{skill_id}/reports",
            json={"reason": "inappropriate", "details": "testing"},
        )
        assert r.status_code == 201, r.text
    finally:
        await reporter_client.aclose()

    # Assert: audit log captured the report submission. We query directly
    # since the audit listener commits its own session.
    await db_session.rollback()  # flush fixture to see listener writes
    rows = (
        await db_session.execute(
            text(
                "SELECT action, target_id, actor_user_id FROM audit_log "
                "WHERE action = 'report.submitted' ORDER BY id DESC LIMIT 1"
            )
        )
    ).one_or_none()
    assert rows is not None
    assert rows[0] == "report.submitted"
    assert rows[1] == skill_id
    assert rows[2] == reporter_id


async def test_public_publish_creates_pending_review_and_approval_publishes_it(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    # Owner publishes PUBLIC — version lands PENDING_REVIEW.
    await _register(async_client, "public_owner")
    zip_bytes = _zip(
        {
            "SKILL.md": b"---\nname: Pub Skill\ndescription: d\nversion: 1.0.0\n---\n",
            "x.py": b"pass",
        }
    )
    pub = await async_client.post(
        "/api/v1/skills/global/publish",
        files={"file": ("pkg.zip", zip_bytes, "application/zip")},
        data={"visibility": "PUBLIC"},
    )
    assert pub.status_code == 201
    version = _data(pub)["version"]
    assert _data(pub)["status"] == "PENDING_REVIEW"

    # Owner submits the version for review.
    submit_body = {
        "skillVersionId": await _resolve_version_id(db_session, _data(pub)["skillId"], version)
    }
    r = await async_client.post("/api/v1/reviews", json=submit_body)
    assert r.status_code == 201, r.text
    review_id = _data(r)["id"]

    # Reviewer account: register + grant SKILL_ADMIN role.
    reviewer_client = AsyncClient(
        transport=async_client._transport,
        base_url="http://testserver",  # type: ignore[attr-defined]
    )
    try:
        reviewer_id = await _register(reviewer_client, "reviewer_user")
        await _grant_role(db_session, reviewer_id, "SKILL_ADMIN")

        review_list = await reviewer_client.get(
            "/api/web/reviews",
            params={"status": "PENDING", "page": 0, "size": 10, "sortDirection": "DESC"},
        )
        assert review_list.status_code == 200, review_list.text
        review_items = _data(review_list)["items"]
        web_review = next((item for item in review_items if item["id"] == review_id), None)
        assert web_review is not None
        assert web_review["namespace"] == "global"
        assert web_review["skillSlug"] == "pub-skill"
        assert web_review["submittedByName"] == "public_owner"

        review_detail = await reviewer_client.get(f"/api/web/reviews/{review_id}")
        assert review_detail.status_code == 200, review_detail.text
        assert _data(review_detail)["skillVersionId"] == submit_body["skillVersionId"]

        skill_detail = await reviewer_client.get(f"/api/web/reviews/{review_id}/skill-detail")
        assert skill_detail.status_code == 200, skill_detail.text
        detail_body = _data(skill_detail)
        assert detail_body["skill"]["namespace"] == "global"
        assert any(file["filePath"] == "x.py" for file in detail_body["files"])

        readme = await reviewer_client.get(f"/api/web/reviews/{review_id}/file", params={"path": "SKILL.md"})
        assert readme.status_code == 200, readme.text
        assert "Pub Skill" in readme.text

        summary = await reviewer_client.get("/api/web/governance/summary")
        assert summary.status_code == 200, summary.text
        assert _data(summary)["pendingReviews"] >= 1

        v1_summary = await reviewer_client.get("/api/v1/governance/summary")
        assert v1_summary.status_code == 200, v1_summary.text
        assert _data(v1_summary)["pendingReviews"] >= 1

        inbox = await reviewer_client.get("/api/web/governance/inbox", params={"page": 0, "size": 10})
        assert inbox.status_code == 200, inbox.text
        assert any(item["type"] == "REVIEW" and item["id"] == review_id for item in _data(inbox)["items"])

        activity = await reviewer_client.get("/api/web/governance/activity", params={"page": 0, "size": 10})
        assert activity.status_code == 200, activity.text
        assert "items" in _data(activity)

        approval = await reviewer_client.post(
            f"/api/v1/reviews/{review_id}/approve", json={"comment": "looks good"}
        )
        assert approval.status_code == 200, approval.text
        assert _data(approval)["status"] == "APPROVED"
    finally:
        await reviewer_client.aclose()

    # The version is now PUBLISHED and the skill has latest_version_id set.
    detail = await async_client.get("/api/v1/skills/global/pub-skill")
    assert detail.status_code == 200
    assert _data(detail)["latestVersionId"] is not None


async def _resolve_version_id(db: AsyncSession, skill_id: int, version: str) -> int:
    row = (
        await db.execute(
            text("SELECT id FROM skill_version WHERE skill_id=:s AND version=:v"),
            {"s": skill_id, "v": version},
        )
    ).scalar_one()
    return int(row)


async def test_audit_log_read_requires_audit_permission(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    user_id = await _register(async_client, "audit_reader")

    # Without the permission, 403.
    r = await async_client.get("/api/v1/admin/audit-logs")
    assert r.status_code == 403

    # Grant AUDITOR and retry.
    await _grant_role(db_session, user_id, "AUDITOR")
    r = await async_client.get("/api/v1/admin/audit-logs")
    assert r.status_code == 200, r.text
    body = _data(r)
    assert "items" in body
    assert isinstance(body["items"], list)
