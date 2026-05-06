"""API tokens, RBAC (role/permission), account merge, password reset, profile change."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from skillhub_api.infra.db.base import Base
from skillhub_api.infra.db.models._common import created_at


class ApiToken(Base):
    __tablename__ = "api_token"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    subject_type: Mapped[str] = mapped_column(String(32), nullable=False, default="USER")
    subject_id: Mapped[str] = mapped_column(String(128), nullable=False)
    user_id: Mapped[str] = mapped_column(String(128), ForeignKey("user_account.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    token_prefix: Mapped[str] = mapped_column(String(16), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    scope_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = created_at()

    __table_args__ = (
        Index("idx_api_token_user_id", "user_id"),
        Index("idx_api_token_hash", "token_hash"),
        Index(
            "uk_api_token_user_active_name",
            "user_id",
            func.lower(text("name")),
            unique=True,
            postgresql_where=text("revoked_at IS NULL"),
        ),
    )


class Role(Base):
    __tablename__ = "role"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(String(512), nullable=True)
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = created_at()


class Permission(Base):
    __tablename__ = "permission"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    code: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    group_code: Mapped[str | None] = mapped_column(String(64), nullable=True)


class RolePermission(Base):
    __tablename__ = "role_permission"

    role_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("role.id"), primary_key=True)
    permission_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("permission.id"), primary_key=True
    )


class UserRoleBinding(Base):
    __tablename__ = "user_role_binding"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128), ForeignKey("user_account.id"), nullable=False)
    role_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("role.id"), nullable=False)
    created_at: Mapped[datetime] = created_at()

    __table_args__ = (
        UniqueConstraint("user_id", "role_id", name="uq_user_role_binding_user_role"),
        Index("idx_user_role_binding_user_id", "user_id"),
    )


class AccountMergeRequest(Base):
    __tablename__ = "account_merge_request"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    primary_user_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("user_account.id"), nullable=False
    )
    secondary_user_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("user_account.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING")
    verification_token: Mapped[str | None] = mapped_column(String(255), nullable=True)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at()

    __table_args__ = (
        Index("idx_merge_primary_status", "primary_user_id", "status"),
        Index(
            "idx_merge_secondary_pending",
            "secondary_user_id",
            unique=True,
            postgresql_where=text("status = 'PENDING'"),
        ),
        Index(
            "idx_merge_token_pending",
            "verification_token",
            postgresql_where=text("status = 'PENDING'"),
        ),
    )


class PasswordResetRequest(Base):
    __tablename__ = "password_reset_request"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("user_account.id", ondelete="CASCADE"),
        nullable=False,
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    code_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    requested_by_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    requested_by_user_id: Mapped[str | None] = mapped_column(
        String(128),
        ForeignKey("user_account.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = created_at()

    __table_args__ = (
        Index("idx_password_reset_request_user_id", "user_id"),
        Index("idx_password_reset_request_expires_at", "expires_at"),
    )


class ProfileChangeRequest(Base):
    __tablename__ = "profile_change_request"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128), ForeignKey("user_account.id"), nullable=False)
    changes: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    old_values: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING")
    machine_result: Mapped[str | None] = mapped_column(String(32), nullable=True)
    machine_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewer_id: Mapped[str | None] = mapped_column(
        String(128), ForeignKey("user_account.id"), nullable=True
    )
    review_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = created_at()
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("idx_pcr_user_id", "user_id"),
        Index("idx_pcr_status", "status"),
        Index("idx_pcr_created", text("created_at DESC")),
        Index("idx_pcr_changes", "changes", postgresql_using="gin"),
    )
