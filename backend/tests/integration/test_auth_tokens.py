"""API token flow against real Postgres.

Ensures:
  * plaintext is returned exactly once on creation,
  * bearer auth resolves the user via the stored hash,
  * name uniqueness is enforced for active tokens,
  * revoking a token blocks further bearer auth.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from skillhub_api.main import create_app

pytestmark = pytest.mark.integration


def _data(response) -> dict | list:
    return response.json()["data"]


@pytest.fixture
def app() -> FastAPI:
    return create_app()


@pytest.fixture
async def async_client(app: FastAPI) -> AsyncClient:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as c:
        yield c


async def _register_and_login(client: AsyncClient, username: str) -> None:
    resp = await client.post(
        "/api/v1/auth/local/register",
        json={"username": username, "password": "passw0rdpass", "email": f"{username}@x.com"},
    )
    assert resp.status_code == 200, resp.text


async def test_token_lifecycle(async_client: AsyncClient) -> None:
    await _register_and_login(async_client, "token_user_1")

    # create
    r = await async_client.post(
        "/api/v1/tokens",
        json={"name": "ci-token", "scope": ["skill:publish"]},
    )
    assert r.status_code == 201, r.text
    payload = _data(r)
    plaintext = payload["token"]
    assert plaintext.startswith("sk_")
    summary = payload
    assert summary["tokenPrefix"] == plaintext[:8]

    # list
    listed = await async_client.get("/api/v1/tokens")
    assert listed.status_code == 200
    listed_payload = _data(listed)
    assert listed_payload["page"] == 0
    assert listed_payload["size"] >= 1
    assert any(t["id"] == summary["id"] for t in listed_payload["items"])

    # bearer auth using a fresh client (no session cookie)
    bearer_client = AsyncClient(
        transport=ASGITransport(app=async_client._transport.app),  # type: ignore[attr-defined]
        base_url="http://testserver",
        headers={"Authorization": f"Bearer {plaintext}"},
    )
    try:
        me = await bearer_client.get("/api/v1/auth/me")
        assert me.status_code == 200
    finally:
        await bearer_client.aclose()

    # conflict on duplicate active name
    dup = await async_client.post("/api/v1/tokens", json={"name": "ci-token"})
    assert dup.status_code == 409

    # revoke
    rev = await async_client.delete(f"/api/v1/tokens/{summary['id']}")
    assert rev.status_code == 204

    # now the bearer token is rejected
    bearer_client = AsyncClient(
        transport=ASGITransport(app=async_client._transport.app),  # type: ignore[attr-defined]
        base_url="http://testserver",
        headers={"Authorization": f"Bearer {plaintext}"},
    )
    try:
        me = await bearer_client.get("/api/v1/auth/me")
        assert me.status_code == 401
    finally:
        await bearer_client.aclose()


async def test_password_reset_request_always_succeeds(async_client: AsyncClient) -> None:
    # Unknown email still returns status=ok so no enumeration leaks.
    r = await async_client.post(
        "/api/v1/auth/local/password-reset/request",
        json={"email": "nobody@example.com"},
    )
    assert r.status_code == 200
    assert _data(r)["status"] == "ok"


async def test_user_profile_get_patch_and_pending_overlay(async_client: AsyncClient) -> None:
    await _register_and_login(async_client, "profile_user_1")

    profile = await async_client.get("/api/v1/user/profile")
    assert profile.status_code == 200, profile.text
    body = _data(profile)
    assert body["displayName"] == "profile_user_1"
    assert body["email"] == "profile_user_1@x.com"
    assert body["fieldPolicies"]["displayName"]["editable"] is True
    assert body["fieldPolicies"]["avatarUrl"]["editable"] is True
    assert body["fieldPolicies"]["email"]["editable"] is False

    invalid = await async_client.patch("/api/v1/user/profile", json={"avatarUrl": "javascript:alert(1)"})
    assert invalid.status_code == 409

    update = await async_client.patch(
        "/api/v1/user/profile",
        json={"displayName": "Profile User", "avatarUrl": "https://example.com/avatar.png"},
    )
    assert update.status_code == 200, update.text
    assert _data(update)["status"] == "PENDING_REVIEW"
    assert _data(update)["pendingFields"]["displayName"] == "Profile User"
    assert _data(update)["pendingFields"]["avatarUrl"] == "https://example.com/avatar.png"

    profile = await async_client.get("/api/v1/user/profile")
    assert profile.status_code == 200, profile.text
    body = _data(profile)
    assert body["displayName"] == "Profile User"
    assert body["avatarUrl"] == "https://example.com/avatar.png"
    assert body["pendingChanges"]["changes"]["displayName"] == "Profile User"
    assert body["pendingChanges"]["changes"]["avatarUrl"] == "https://example.com/avatar.png"
