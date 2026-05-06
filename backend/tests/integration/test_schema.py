"""Verify that the Alembic baseline brings up the full V40-equivalent schema.

Requires Docker (pytest-testcontainers). Marked `integration` so it's excluded
from the default `make test` which only runs unit tests.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration


EXPECTED_TABLES = {
    "user_account",
    "identity_binding",
    "local_credential",
    "api_token",
    "role",
    "permission",
    "role_permission",
    "user_role_binding",
    "account_merge_request",
    "password_reset_request",
    "profile_change_request",
    "namespace",
    "namespace_member",
    "skill",
    "skill_version",
    "skill_file",
    "skill_tag",
    "skill_version_stats",
    "label_definition",
    "label_translation",
    "skill_label",
    "skill_search_document",
    "skill_star",
    "skill_rating",
    "skill_subscription",
    "review_task",
    "promotion_request",
    "skill_report",
    "user_notification",
    "notification",
    "notification_preference",
    "audit_log",
    "idempotency_record",
    "security_audit",
    "skill_storage_delete_compensation",
}


async def _tables(session: AsyncSession) -> set[str]:
    result = await session.execute(
        text(
            "SELECT tablename FROM pg_tables "
            "WHERE schemaname = 'public' AND tablename != 'alembic_version'"
        )
    )
    return {row[0] for row in result}


async def test_all_expected_tables_present(db_session: AsyncSession) -> None:
    tables = await _tables(db_session)
    assert EXPECTED_TABLES.issubset(tables), f"missing: {EXPECTED_TABLES - tables}"


async def test_seed_roles_and_permissions(db_session: AsyncSession) -> None:
    role_count = (await db_session.execute(text("SELECT COUNT(*) FROM role"))).scalar_one()
    assert role_count == 4

    perm_count = (await db_session.execute(text("SELECT COUNT(*) FROM permission"))).scalar_one()
    assert perm_count == 8

    namespace = (await db_session.execute(text("SELECT slug, type FROM namespace"))).one()
    assert namespace == ("global", "GLOBAL")


async def test_search_vector_is_generated_stored(db_session: AsyncSession) -> None:
    """search_vector should be a STORED generated column driven by `simple` tsvector."""
    row = (
        await db_session.execute(
            text(
                """
                SELECT attgenerated
                FROM pg_attribute a
                JOIN pg_class c ON a.attrelid = c.oid
                WHERE c.relname = 'skill_search_document' AND a.attname = 'search_vector'
                """
            )
        )
    ).one()
    assert row[0] in ("s", b"s")  # 's' = STORED generated column


async def test_skill_rating_score_bounds(db_session: AsyncSession) -> None:
    # Prepare a user, namespace, skill so the FK chain holds, then assert that
    # an out-of-range rating is rejected by the CHECK constraint.
    await db_session.execute(
        text("INSERT INTO user_account (id, display_name) VALUES ('u1', 'User One')")
    )
    namespace_id = (
        await db_session.execute(text("SELECT id FROM namespace WHERE slug='global'"))
    ).scalar_one()
    await db_session.execute(
        text("INSERT INTO skill (namespace_id, slug, owner_id) VALUES (:nid, 'demo', 'u1')"),
        {"nid": namespace_id},
    )
    skill_id = (
        await db_session.execute(text("SELECT id FROM skill WHERE slug='demo'"))
    ).scalar_one()

    with pytest.raises(Exception, match="score"):  # CHECK constraint surfaces as DBAPIError
        await db_session.execute(
            text("INSERT INTO skill_rating (skill_id, user_id, score) VALUES (:sid, 'u1', 6)"),
            {"sid": skill_id},
        )
