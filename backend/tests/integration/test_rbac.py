"""RBAC permission resolution test — exercises the Super-Admin wildcard and
the role→permission join chain used by ``require_permission``.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from skillhub_api.deps import _user_permissions
from skillhub_api.infra.db.models.auth import Role

pytestmark = pytest.mark.integration


async def _make_user(db: AsyncSession) -> str:
    uid = uuid.uuid4().hex
    await db.execute(
        text("INSERT INTO user_account (id, display_name) VALUES (:id, :dn)"),
        {"id": uid, "dn": "rbac-test"},
    )
    return uid


async def test_user_without_roles_has_no_permissions(db_session: AsyncSession) -> None:
    uid = await _make_user(db_session)
    perms = await _user_permissions(db_session, uid)
    assert perms == set()


async def test_skill_admin_grants_three_permissions(db_session: AsyncSession) -> None:
    uid = await _make_user(db_session)
    role = (await db_session.execute(select(Role).where(Role.code == "SKILL_ADMIN"))).scalar_one()
    await db_session.execute(
        text("INSERT INTO user_role_binding (user_id, role_id) VALUES (:u, :r)"),
        {"u": uid, "r": role.id},
    )
    perms = await _user_permissions(db_session, uid)
    assert perms == {"review:approve", "skill:manage", "promotion:approve"}


async def test_super_admin_is_wildcard(db_session: AsyncSession) -> None:
    uid = await _make_user(db_session)
    role = (await db_session.execute(select(Role).where(Role.code == "SUPER_ADMIN"))).scalar_one()
    await db_session.execute(
        text("INSERT INTO user_role_binding (user_id, role_id) VALUES (:u, :r)"),
        {"u": uid, "r": role.id},
    )
    perms = await _user_permissions(db_session, uid)
    # All 8 seeded permissions.
    assert len(perms) == 8
    assert "audit:read" in perms
