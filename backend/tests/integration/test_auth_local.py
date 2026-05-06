"""End-to-end auth tests against a real Postgres via testcontainers.

Covers the golden path (register → login → me → change-password → login) and
the critical failure modes (wrong password increments counter, 5 strikes
locks the account).
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from skillhub_api.domain.auth import MAX_FAILED_ATTEMPTS
from skillhub_api.main import create_app

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]


def _unique_username(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:8]}"


def _data(response) -> dict:
    return response.json()["data"]


@pytest.fixture
def app() -> FastAPI:
    return create_app()


@pytest.fixture
async def async_client(app: FastAPI) -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


async def _cleanup(db_session: AsyncSession, username: str) -> None:
    await db_session.execute(
        text(
            """
            DELETE FROM local_credential WHERE username = :u;
            DELETE FROM user_account WHERE id IN (
              SELECT user_id FROM local_credential WHERE username = :u
            );
            """
        ),
        {"u": username},
    )


async def test_register_login_me_roundtrip(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    username = _unique_username("alice_py")
    register = await async_client.post(
        "/api/v1/auth/local/register",
        json={
            "username": username,
            "password": "s3cretpass",
            "email": f"{username}@example.com",
        },
    )
    assert register.status_code == 200, register.text
    body = _data(register)
    assert body["displayName"] == username
    assert body["platformRoles"] == []
    assert "avatarUrl" in body
    assert "oauthProvider" in body

    # /me should now return the logged-in user (session cookie set).
    me = await async_client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert _data(me)["userId"] == body["userId"]

    # The browser-facing logout alias clears the same session.
    logout = await async_client.post("/api/v1/auth/logout")
    assert logout.status_code == 204
    assert (await async_client.get("/api/v1/auth/me")).status_code == 401

    # login works with the same credentials.
    login = await async_client.post(
        "/api/v1/auth/local/login",
        json={"username": username, "password": "s3cretpass"},
    )
    assert login.status_code == 200
    assert (await async_client.get("/api/v1/auth/me")).status_code == 200


async def test_wrong_password_does_not_establish_session(async_client: AsyncClient) -> None:
    username = _unique_username("bob_py")
    await async_client.post(
        "/api/v1/auth/local/register",
        json={
            "username": username,
            "password": "goodpassword",
            "email": f"{username}@example.com",
        },
    )
    await async_client.post("/api/v1/auth/local/logout")

    r = await async_client.post(
        "/api/v1/auth/local/login",
        json={"username": username, "password": "wrong"},
    )
    assert r.status_code == 401
    assert (await async_client.get("/api/v1/auth/me")).status_code == 401


async def test_lockout_after_max_failures(async_client: AsyncClient) -> None:
    username = _unique_username("carol_py")
    await async_client.post(
        "/api/v1/auth/local/register",
        json={
            "username": username,
            "password": "goodpassword",
            "email": f"{username}@example.com",
        },
    )
    await async_client.post("/api/v1/auth/local/logout")

    for _ in range(MAX_FAILED_ATTEMPTS):
        r = await async_client.post(
            "/api/v1/auth/local/login",
            json={"username": username, "password": "wrong"},
        )
        assert r.status_code == 401

    # MAX+1 attempt: now returns 403 ACCOUNT_LOCKED even with correct password.
    locked = await async_client.post(
        "/api/v1/auth/local/login",
        json={"username": username, "password": "goodpassword"},
    )
    assert locked.status_code == 403
    assert locked.json()["errorCode"] == "ACCOUNT_LOCKED"


async def test_change_password_invalidates_old(async_client: AsyncClient) -> None:
    username = _unique_username("dan_py")
    await async_client.post(
        "/api/v1/auth/local/register",
        json={
            "username": username,
            "password": "originalpass",
            "email": f"{username}@example.com",
        },
    )
    r = await async_client.post(
        "/api/v1/auth/local/change-password",
        json={"currentPassword": "originalpass", "newPassword": "rotatedpass"},
    )
    assert r.status_code == 204
    await async_client.post("/api/v1/auth/local/logout")

    assert (
        await async_client.post(
            "/api/v1/auth/local/login",
            json={"username": username, "password": "originalpass"},
        )
    ).status_code == 401

    ok = await async_client.post(
        "/api/v1/auth/local/login",
        json={"username": username, "password": "rotatedpass"},
    )
    assert ok.status_code == 200
