"""Initial schema (behaviorally equivalent to Flyway V40).

Created from scratch — not a line-by-line port of the 40 Flyway migrations.
All TIMESTAMPTZ conversions (V16-V26, V36) are applied upfront; all column
expansions (V9, V30, V31) use the final type; all late-added columns
(V14, V15, V32, V40) are part of the initial CREATE TABLE.

Rationale: user opted for a brand-new database with no data migration, so
preserving the 40-step history serves no operational purpose — a single
clean baseline is easier to reason about and review.

Revision ID: 0001_initial_schema_v40
Revises:
Create Date: 2026-05-06
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial_schema_v40"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_SEARCH_VECTOR_EXPR = (
    "setweight(to_tsvector('simple', coalesce(title, '')), 'A') || "
    "setweight(to_tsvector('simple', coalesce(summary, '')), 'B') || "
    "setweight(to_tsvector('simple', coalesce(keywords, '')), 'B') || "
    "setweight(to_tsvector('simple', coalesce(search_text, '')), 'C')"
)


def upgrade() -> None:
    # ---- user_account ----
    op.create_table(
        "user_account",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("display_name", sa.String(128), nullable=False),
        sa.Column("email", sa.String(256)),
        sa.Column("avatar_url", sa.String(512)),
        sa.Column("status", sa.String(32), nullable=False, server_default="ACTIVE"),
        sa.Column("merged_to_user_id", sa.String(128)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index("idx_user_account_email", "user_account", ["email"])
    op.create_index("idx_user_account_status", "user_account", ["status"])

    # ---- identity_binding ----
    op.create_table(
        "identity_binding",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "user_id", sa.String(128), sa.ForeignKey("user_account.id"), nullable=False
        ),
        sa.Column("provider_code", sa.String(64), nullable=False),
        sa.Column("subject", sa.String(256), nullable=False),
        sa.Column("login_name", sa.String(128)),
        sa.Column("extra_json", postgresql.JSONB()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint(
            "provider_code", "subject", name="uq_identity_binding_provider_subject"
        ),
    )
    op.create_index("idx_identity_binding_user_id", "identity_binding", ["user_id"])

    # ---- local_credential ----
    op.create_table(
        "local_credential",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "user_id", sa.String(128), sa.ForeignKey("user_account.id"), nullable=False
        ),
        sa.Column("username", sa.String(64), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("failed_attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("locked_until", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index("idx_local_credential_username", "local_credential", ["username"], unique=True)
    op.create_index("idx_local_credential_user_id", "local_credential", ["user_id"], unique=True)

    # ---- api_token ----
    op.create_table(
        "api_token",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("subject_type", sa.String(32), nullable=False, server_default="USER"),
        sa.Column("subject_id", sa.String(128), nullable=False),
        sa.Column(
            "user_id", sa.String(128), sa.ForeignKey("user_account.id"), nullable=False
        ),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("token_prefix", sa.String(16), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("scope_json", postgresql.JSONB(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("last_used_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index("idx_api_token_user_id", "api_token", ["user_id"])
    op.create_index("idx_api_token_hash", "api_token", ["token_hash"])
    op.execute(
        "CREATE UNIQUE INDEX uk_api_token_user_active_name "
        "ON api_token (user_id, LOWER(name)) "
        "WHERE revoked_at IS NULL"
    )

    # ---- role / permission / role_permission / user_role_binding ----
    op.create_table(
        "role",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("code", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("description", sa.String(512)),
        sa.Column("is_system", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_table(
        "permission",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("code", sa.String(128), nullable=False, unique=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("group_code", sa.String(64)),
    )
    op.create_table(
        "role_permission",
        sa.Column("role_id", sa.BigInteger, sa.ForeignKey("role.id"), primary_key=True),
        sa.Column(
            "permission_id", sa.BigInteger, sa.ForeignKey("permission.id"), primary_key=True
        ),
    )
    op.create_table(
        "user_role_binding",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "user_id", sa.String(128), sa.ForeignKey("user_account.id"), nullable=False
        ),
        sa.Column("role_id", sa.BigInteger, sa.ForeignKey("role.id"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint("user_id", "role_id", name="uq_user_role_binding_user_role"),
    )
    op.create_index("idx_user_role_binding_user_id", "user_role_binding", ["user_id"])

    # ---- account_merge_request ----
    op.create_table(
        "account_merge_request",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "primary_user_id", sa.String(128), sa.ForeignKey("user_account.id"), nullable=False
        ),
        sa.Column(
            "secondary_user_id", sa.String(128), sa.ForeignKey("user_account.id"), nullable=False
        ),
        sa.Column("status", sa.String(32), nullable=False, server_default="PENDING"),
        sa.Column("verification_token", sa.String(255)),
        sa.Column("token_expires_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index("idx_merge_primary_status", "account_merge_request", ["primary_user_id", "status"])
    op.execute(
        "CREATE UNIQUE INDEX idx_merge_secondary_pending "
        "ON account_merge_request (secondary_user_id) WHERE status = 'PENDING'"
    )
    op.execute(
        "CREATE INDEX idx_merge_token_pending "
        "ON account_merge_request (verification_token) WHERE status = 'PENDING'"
    )

    # ---- password_reset_request ----
    op.create_table(
        "password_reset_request",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.String(128),
            sa.ForeignKey("user_account.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("code_hash", sa.String(255), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
        sa.Column("requested_by_admin", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column(
            "requested_by_user_id",
            sa.String(128),
            sa.ForeignKey("user_account.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index("idx_password_reset_request_user_id", "password_reset_request", ["user_id"])
    op.create_index(
        "idx_password_reset_request_expires_at", "password_reset_request", ["expires_at"]
    )

    # ---- profile_change_request ----
    op.create_table(
        "profile_change_request",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "user_id", sa.String(128), sa.ForeignKey("user_account.id"), nullable=False
        ),
        sa.Column("changes", postgresql.JSONB(), nullable=False),
        sa.Column("old_values", postgresql.JSONB()),
        sa.Column("status", sa.String(32), nullable=False, server_default="PENDING"),
        sa.Column("machine_result", sa.String(32)),
        sa.Column("machine_reason", sa.Text),
        sa.Column(
            "reviewer_id", sa.String(128), sa.ForeignKey("user_account.id"), nullable=True
        ),
        sa.Column("review_comment", sa.Text),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
    )
    op.create_index("idx_pcr_user_id", "profile_change_request", ["user_id"])
    op.create_index("idx_pcr_status", "profile_change_request", ["status"])
    op.execute("CREATE INDEX idx_pcr_created ON profile_change_request (created_at DESC)")
    op.execute(
        "CREATE INDEX idx_pcr_changes ON profile_change_request USING GIN (changes)"
    )

    # ---- namespace / namespace_member ----
    op.create_table(
        "namespace",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("slug", sa.String(64), nullable=False, unique=True),
        sa.Column("display_name", sa.String(128), nullable=False),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("avatar_url", sa.String(512)),
        sa.Column("status", sa.String(32), nullable=False, server_default="ACTIVE"),
        sa.Column("created_by", sa.String(128), sa.ForeignKey("user_account.id")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_table(
        "namespace_member",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "namespace_id", sa.BigInteger, sa.ForeignKey("namespace.id"), nullable=False
        ),
        sa.Column(
            "user_id", sa.String(128), sa.ForeignKey("user_account.id"), nullable=False
        ),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint(
            "namespace_id", "user_id", name="uq_namespace_member_namespace_user"
        ),
    )
    op.create_index("idx_namespace_member_user_id", "namespace_member", ["user_id"])
    op.create_index("idx_namespace_member_namespace_id", "namespace_member", ["namespace_id"])

    # ---- skill + skill_version + skill_file + skill_tag + skill_version_stats ----
    # skill_version has a FK from skill.latest_version_id, so we create skill first
    # without that FK and add it after skill_version exists.
    op.create_table(
        "skill",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "namespace_id", sa.BigInteger, sa.ForeignKey("namespace.id"), nullable=False
        ),
        sa.Column("slug", sa.String(128), nullable=False),
        sa.Column("display_name", sa.String(256)),
        sa.Column("summary", sa.Text),
        sa.Column(
            "owner_id", sa.String(128), sa.ForeignKey("user_account.id"), nullable=False
        ),
        sa.Column("source_skill_id", sa.BigInteger),
        sa.Column("visibility", sa.String(32), nullable=False, server_default="PUBLIC"),
        sa.Column("status", sa.String(32), nullable=False, server_default="ACTIVE"),
        sa.Column("latest_version_id", sa.BigInteger),
        sa.Column("download_count", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("subscription_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("star_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("rating_avg", sa.Numeric(3, 2), nullable=False, server_default=sa.text("0.00")),
        sa.Column("rating_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("hidden", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("hidden_at", sa.DateTime(timezone=True)),
        sa.Column("hidden_by", sa.String(128), sa.ForeignKey("user_account.id")),
        sa.Column("created_by", sa.String(128), sa.ForeignKey("user_account.id")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("updated_by", sa.String(128), sa.ForeignKey("user_account.id")),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint(
            "namespace_id", "slug", "owner_id", name="uq_skill_namespace_slug_owner"
        ),
    )
    op.create_index("idx_skill_namespace_status", "skill", ["namespace_id", "status"])
    op.execute("CREATE INDEX idx_skill_hidden ON skill (hidden) WHERE hidden = TRUE")
    op.execute(
        "CREATE INDEX idx_skill_active_visible_updated "
        "ON skill (updated_at DESC, id DESC) "
        "WHERE status = 'ACTIVE' AND hidden = FALSE"
    )
    op.execute(
        "CREATE INDEX idx_skill_active_visible_downloads "
        "ON skill (download_count DESC, updated_at DESC, id DESC) "
        "WHERE status = 'ACTIVE' AND hidden = FALSE"
    )
    op.execute(
        "CREATE INDEX idx_skill_active_visible_rating "
        "ON skill (rating_avg DESC, updated_at DESC, id DESC) "
        "WHERE status = 'ACTIVE' AND hidden = FALSE"
    )

    op.create_table(
        "skill_version",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("skill_id", sa.BigInteger, sa.ForeignKey("skill.id"), nullable=False),
        sa.Column("version", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="DRAFT"),
        sa.Column("changelog", sa.Text),
        sa.Column("parsed_metadata_json", postgresql.JSONB()),
        sa.Column("manifest_json", postgresql.JSONB()),
        sa.Column("file_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_size", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("bundle_ready", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("download_ready", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("requested_visibility", sa.String(20)),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("created_by", sa.String(128), sa.ForeignKey("user_account.id")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("yanked_at", sa.DateTime(timezone=True)),
        sa.Column("yanked_by", sa.String(128), sa.ForeignKey("user_account.id")),
        sa.Column("yank_reason", sa.Text),
        sa.UniqueConstraint("skill_id", "version", name="uq_skill_version_skill_version"),
    )
    op.create_index(
        "idx_skill_version_skill_status", "skill_version", ["skill_id", "status"]
    )
    op.create_foreign_key(
        "fk_skill_latest_version",
        "skill",
        "skill_version",
        ["latest_version_id"],
        ["id"],
    )

    op.create_table(
        "skill_file",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("version_id", sa.BigInteger, sa.ForeignKey("skill_version.id"), nullable=False),
        sa.Column("file_path", sa.String(512), nullable=False),
        sa.Column("file_size", sa.BigInteger, nullable=False),
        sa.Column("content_type", sa.String(128)),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("storage_key", sa.String(512), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint("version_id", "file_path", name="uq_skill_file_version_path"),
    )

    op.create_table(
        "skill_tag",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("skill_id", sa.BigInteger, sa.ForeignKey("skill.id"), nullable=False),
        sa.Column("tag_name", sa.String(64), nullable=False),
        sa.Column("version_id", sa.BigInteger, sa.ForeignKey("skill_version.id"), nullable=False),
        sa.Column("created_by", sa.String(128), sa.ForeignKey("user_account.id")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint("skill_id", "tag_name", name="uq_skill_tag_skill_name"),
    )

    op.create_table(
        "skill_version_stats",
        sa.Column(
            "skill_version_id",
            sa.BigInteger,
            sa.ForeignKey("skill_version.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "skill_id", sa.BigInteger, sa.ForeignKey("skill.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("download_count", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index("idx_skill_version_stats_skill_id", "skill_version_stats", ["skill_id"])

    # ---- labels ----
    op.create_table(
        "label_definition",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("slug", sa.String(64), nullable=False, unique=True),
        sa.Column("type", sa.String(16), nullable=False),
        sa.Column(
            "visible_in_filter", sa.Boolean, nullable=False, server_default=sa.text("true")
        ),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_by", sa.String(128), sa.ForeignKey("user_account.id")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint("type IN ('RECOMMENDED', 'PRIVILEGED')", name="label_definition_type_check"),
    )
    op.create_index(
        "idx_label_definition_visible_sort",
        "label_definition",
        ["visible_in_filter", "type", "sort_order", "id"],
    )
    op.create_table(
        "label_translation",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "label_id",
            sa.BigInteger,
            sa.ForeignKey("label_definition.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("locale", sa.String(16), nullable=False),
        sa.Column("display_name", sa.String(128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint("label_id", "locale", name="uq_label_translation_label_locale"),
    )
    op.create_index("idx_label_translation_label_id", "label_translation", ["label_id"])
    op.create_table(
        "skill_label",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "skill_id",
            sa.BigInteger,
            sa.ForeignKey("skill.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "label_id",
            sa.BigInteger,
            sa.ForeignKey("label_definition.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("created_by", sa.String(128), sa.ForeignKey("user_account.id")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint("skill_id", "label_id", name="uq_skill_label_skill_label"),
    )
    op.create_index("idx_skill_label_label_id", "skill_label", ["label_id"])
    op.create_index("idx_skill_label_skill_id", "skill_label", ["skill_id"])

    # ---- skill_search_document (generated tsvector column) ----
    op.execute(
        f"""
        CREATE TABLE skill_search_document (
            id BIGSERIAL PRIMARY KEY,
            skill_id BIGINT NOT NULL UNIQUE REFERENCES skill(id),
            namespace_id BIGINT NOT NULL,
            namespace_slug VARCHAR(64) NOT NULL,
            owner_id VARCHAR(128) NOT NULL,
            title VARCHAR(512),
            summary TEXT,
            keywords TEXT,
            search_text TEXT,
            semantic_vector TEXT,
            visibility VARCHAR(32) NOT NULL,
            status VARCHAR(32) NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            search_vector tsvector GENERATED ALWAYS AS (
                {_SEARCH_VECTOR_EXPR}
            ) STORED
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_search_vector ON skill_search_document USING GIN (search_vector)"
    )
    op.create_index("idx_search_doc_namespace", "skill_search_document", ["namespace_id"])
    op.create_index("idx_search_doc_visibility", "skill_search_document", ["visibility"])

    # ---- social: stars, ratings, subscriptions ----
    op.create_table(
        "skill_star",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("skill_id", sa.BigInteger, sa.ForeignKey("skill.id"), nullable=False),
        sa.Column(
            "user_id", sa.String(128), sa.ForeignKey("user_account.id"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint("skill_id", "user_id", name="uq_skill_star_skill_user"),
    )
    op.create_index("idx_skill_star_user_id", "skill_star", ["user_id"])
    op.create_index("idx_skill_star_skill_id", "skill_star", ["skill_id"])

    op.create_table(
        "skill_rating",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("skill_id", sa.BigInteger, sa.ForeignKey("skill.id"), nullable=False),
        sa.Column(
            "user_id", sa.String(128), sa.ForeignKey("user_account.id"), nullable=False
        ),
        sa.Column("score", sa.SmallInteger, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint("score >= 1 AND score <= 5", name="skill_rating_score_check"),
        sa.UniqueConstraint("skill_id", "user_id", name="uq_skill_rating_skill_user"),
    )
    op.create_index("idx_skill_rating_skill_id", "skill_rating", ["skill_id"])

    op.create_table(
        "skill_subscription",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "skill_id",
            sa.BigInteger,
            sa.ForeignKey("skill.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", sa.String(128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("skill_id", "user_id", name="uk_skill_subscription"),
    )
    op.execute(
        "CREATE INDEX idx_skill_subscription_user ON skill_subscription (user_id, created_at DESC)"
    )
    op.create_index("idx_skill_subscription_skill", "skill_subscription", ["skill_id"])

    # ---- governance: review_task, promotion_request, skill_report ----
    op.create_table(
        "review_task",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "skill_version_id", sa.BigInteger, sa.ForeignKey("skill_version.id"), nullable=False
        ),
        sa.Column(
            "namespace_id", sa.BigInteger, sa.ForeignKey("namespace.id"), nullable=False
        ),
        sa.Column("status", sa.String(32), nullable=False, server_default="PENDING"),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column(
            "submitted_by", sa.String(128), sa.ForeignKey("user_account.id"), nullable=False
        ),
        sa.Column("reviewed_by", sa.String(128), sa.ForeignKey("user_account.id")),
        sa.Column("review_comment", sa.Text),
        sa.Column(
            "submitted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
    )
    op.create_index("idx_review_task_namespace_status", "review_task", ["namespace_id", "status"])
    op.create_index(
        "idx_review_task_submitted_by_status", "review_task", ["submitted_by", "status"]
    )
    op.execute(
        "CREATE UNIQUE INDEX idx_review_task_version_pending "
        "ON review_task (skill_version_id) WHERE status = 'PENDING'"
    )

    op.create_table(
        "promotion_request",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "source_skill_id", sa.BigInteger, sa.ForeignKey("skill.id"), nullable=False
        ),
        sa.Column(
            "source_version_id", sa.BigInteger, sa.ForeignKey("skill_version.id"), nullable=False
        ),
        sa.Column(
            "target_namespace_id", sa.BigInteger, sa.ForeignKey("namespace.id"), nullable=False
        ),
        sa.Column("target_skill_id", sa.BigInteger, sa.ForeignKey("skill.id")),
        sa.Column("status", sa.String(32), nullable=False, server_default="PENDING"),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column(
            "submitted_by", sa.String(128), sa.ForeignKey("user_account.id"), nullable=False
        ),
        sa.Column("reviewed_by", sa.String(128), sa.ForeignKey("user_account.id")),
        sa.Column("review_comment", sa.Text),
        sa.Column(
            "submitted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
    )
    op.create_index("idx_promotion_request_source_skill", "promotion_request", ["source_skill_id"])
    op.create_index("idx_promotion_request_status", "promotion_request", ["status"])
    op.execute(
        "CREATE UNIQUE INDEX idx_promotion_request_version_pending "
        "ON promotion_request (source_version_id) WHERE status = 'PENDING'"
    )

    op.create_table(
        "skill_report",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "skill_id",
            sa.BigInteger,
            sa.ForeignKey("skill.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "namespace_id",
            sa.BigInteger,
            sa.ForeignKey("namespace.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("reporter_id", sa.String(128), nullable=False),
        sa.Column("reason", sa.String(200), nullable=False),
        sa.Column("details", sa.Text),
        sa.Column("status", sa.String(20), nullable=False, server_default="PENDING"),
        sa.Column("handled_by", sa.String(128)),
        sa.Column("handle_comment", sa.Text),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("handled_at", sa.DateTime(timezone=True)),
    )
    op.execute(
        "CREATE INDEX idx_skill_report_status_created_at "
        "ON skill_report (status, created_at DESC)"
    )
    op.create_index("idx_skill_report_skill_id", "skill_report", ["skill_id"])

    # ---- notifications ----
    op.create_table(
        "user_notification",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(128), nullable=False),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("entity_type", sa.String(64), nullable=False),
        sa.Column("entity_id", sa.BigInteger, nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("body_json", sa.Text),
        sa.Column("status", sa.String(20), nullable=False, server_default="UNREAD"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("read_at", sa.DateTime(timezone=True)),
    )
    op.execute(
        "CREATE INDEX idx_user_notification_user_created_at "
        "ON user_notification (user_id, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX idx_user_notification_user_status "
        "ON user_notification (user_id, status, created_at DESC)"
    )

    op.create_table(
        "notification",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("recipient_id", sa.String(128), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("body_json", sa.Text),
        sa.Column("entity_type", sa.String(64)),
        sa.Column("entity_id", sa.BigInteger),
        sa.Column("status", sa.String(20), nullable=False, server_default="UNREAD"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("read_at", sa.DateTime(timezone=True)),
    )
    op.execute(
        "CREATE INDEX idx_notification_recipient_created "
        "ON notification (recipient_id, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX idx_notification_recipient_status "
        "ON notification (recipient_id, status, created_at DESC)"
    )

    op.create_table(
        "notification_preference",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(128), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("channel", sa.String(32), nullable=False),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.UniqueConstraint(
            "user_id", "category", "channel", name="uq_notification_preference_user_cat_chan"
        ),
    )

    # ---- audit_log ----
    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("actor_user_id", sa.String(128), sa.ForeignKey("user_account.id")),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("target_type", sa.String(64)),
        sa.Column("target_id", sa.BigInteger),
        sa.Column("request_id", sa.String(64)),
        sa.Column("client_ip", sa.String(64)),
        sa.Column("user_agent", sa.String(512)),
        sa.Column("detail_json", postgresql.JSONB()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index("idx_audit_log_actor", "audit_log", ["actor_user_id"])
    op.create_index("idx_audit_log_created_at", "audit_log", ["created_at"])
    op.create_index("idx_audit_log_request_id", "audit_log", ["request_id"])
    op.execute(
        "CREATE INDEX idx_audit_log_actor_time ON audit_log (actor_user_id, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX idx_audit_log_action_time ON audit_log (action, created_at DESC)"
    )

    # ---- idempotency_record ----
    op.create_table(
        "idempotency_record",
        sa.Column("request_id", sa.String(64), primary_key=True),
        sa.Column("resource_type", sa.String(64), nullable=False),
        sa.Column("resource_id", sa.BigInteger),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("response_status_code", sa.Integer),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("idx_idempotency_record_expires_at", "idempotency_record", ["expires_at"])
    op.create_index(
        "idx_idempotency_record_status_created", "idempotency_record", ["status", "created_at"]
    )

    # ---- security_audit (no FK — V38 dropped it) ----
    op.create_table(
        "security_audit",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("skill_version_id", sa.BigInteger),
        sa.Column("scan_id", sa.String(100)),
        sa.Column(
            "scanner_type", sa.String(50), nullable=False, server_default="skill-scanner"
        ),
        sa.Column("verdict", sa.String(20), nullable=False),
        sa.Column("is_safe", sa.Boolean, nullable=False),
        sa.Column("max_severity", sa.String(20)),
        sa.Column("findings_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "findings", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column("scan_duration_seconds", sa.Double),
        sa.Column("scanned_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
    )
    op.execute(
        "CREATE INDEX idx_security_audit_version_active "
        "ON security_audit (skill_version_id, deleted_at) WHERE deleted_at IS NULL"
    )
    op.create_index("idx_security_audit_verdict", "security_audit", ["verdict"])
    op.execute(
        "CREATE INDEX idx_security_audit_version_type_latest "
        "ON security_audit (skill_version_id, scanner_type, created_at DESC) "
        "WHERE deleted_at IS NULL"
    )

    # ---- skill_storage_delete_compensation ----
    op.create_table(
        "skill_storage_delete_compensation",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("skill_id", sa.BigInteger),
        sa.Column("namespace", sa.String(128), nullable=False),
        sa.Column("slug", sa.String(128), nullable=False),
        sa.Column("storage_keys_json", sa.Text, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="PENDING"),
        sa.Column("attempt_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "idx_skill_storage_delete_comp_status_created",
        "skill_storage_delete_compensation",
        ["status", "created_at"],
    )

    # ---- seed data: system roles, permissions, bindings, global namespace ----
    op.execute(
        """
        INSERT INTO role (code, name, description, is_system) VALUES
          ('SUPER_ADMIN', 'Super Admin', 'Full privileges', TRUE),
          ('SKILL_ADMIN', 'Skill Admin', 'Global namespace review, promotion review, hide/yank', TRUE),
          ('USER_ADMIN', 'User Admin', 'User approval, ban/unban, role assignment', TRUE),
          ('AUDITOR', 'Auditor', 'Read audit logs', TRUE)
        """
    )
    op.execute(
        """
        INSERT INTO permission (code, name, group_code) VALUES
          ('skill:publish', 'Publish skill', 'skill'),
          ('skill:manage', 'Manage skill', 'skill'),
          ('skill:promote', 'Promote to global', 'skill'),
          ('review:approve', 'Approve review', 'review'),
          ('promotion:approve', 'Approve promotion', 'promotion'),
          ('user:manage', 'Manage users', 'user'),
          ('user:approve', 'Approve user onboarding', 'user'),
          ('audit:read', 'Read audit log', 'audit')
        """
    )
    op.execute(
        """
        INSERT INTO role_permission (role_id, permission_id)
        SELECT r.id, p.id FROM role r, permission p
        WHERE r.code = 'SKILL_ADMIN'
          AND p.code IN ('review:approve', 'skill:manage', 'promotion:approve')
        """
    )
    op.execute(
        """
        INSERT INTO role_permission (role_id, permission_id)
        SELECT r.id, p.id FROM role r, permission p
        WHERE r.code = 'USER_ADMIN' AND p.code IN ('user:manage', 'user:approve')
        """
    )
    op.execute(
        """
        INSERT INTO role_permission (role_id, permission_id)
        SELECT r.id, p.id FROM role r, permission p
        WHERE r.code = 'AUDITOR' AND p.code = 'audit:read'
        """
    )
    op.execute(
        """
        INSERT INTO namespace (slug, display_name, type, description, status)
        VALUES ('global', 'Global', 'GLOBAL', 'Platform-level public namespace', 'ACTIVE')
        """
    )


def downgrade() -> None:
    # Reverse order to respect FK dependencies.
    op.drop_table("skill_storage_delete_compensation")
    op.drop_table("security_audit")
    op.drop_table("idempotency_record")
    op.drop_table("audit_log")
    op.drop_table("notification_preference")
    op.drop_table("notification")
    op.drop_table("user_notification")
    op.drop_table("skill_report")
    op.drop_table("promotion_request")
    op.drop_table("review_task")
    op.drop_table("skill_subscription")
    op.drop_table("skill_rating")
    op.drop_table("skill_star")
    op.execute("DROP TABLE IF EXISTS skill_search_document")
    op.drop_table("skill_label")
    op.drop_table("label_translation")
    op.drop_table("label_definition")
    op.drop_table("skill_version_stats")
    op.drop_table("skill_tag")
    op.drop_table("skill_file")
    op.drop_constraint("fk_skill_latest_version", "skill", type_="foreignkey")
    op.drop_table("skill_version")
    op.drop_table("skill")
    op.drop_table("namespace_member")
    op.drop_table("namespace")
    op.drop_table("profile_change_request")
    op.drop_table("password_reset_request")
    op.drop_table("account_merge_request")
    op.drop_table("user_role_binding")
    op.drop_table("role_permission")
    op.drop_table("permission")
    op.drop_table("role")
    op.drop_table("api_token")
    op.drop_table("local_credential")
    op.drop_table("identity_binding")
    op.drop_table("user_account")
