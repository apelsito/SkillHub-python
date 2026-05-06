"""User account + identity tables."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from skillhub_api.infra.db.base import Base
from skillhub_api.infra.db.models._common import created_at, updated_at


class UserAccount(Base):
    __tablename__ = "user_account"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    email: Mapped[str | None] = mapped_column(String(256), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACTIVE")
    merged_to_user_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = created_at()
    updated_at: Mapped[datetime] = updated_at()

    __table_args__ = (
        Index("idx_user_account_email", "email"),
        Index("idx_user_account_status", "status"),
    )


class IdentityBinding(Base):
    __tablename__ = "identity_binding"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128), ForeignKey("user_account.id"), nullable=False)
    provider_code: Mapped[str] = mapped_column(String(64), nullable=False)
    subject: Mapped[str] = mapped_column(String(256), nullable=False)
    login_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    extra_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = created_at()
    updated_at: Mapped[datetime] = updated_at()

    __table_args__ = (
        UniqueConstraint("provider_code", "subject", name="uq_identity_binding_provider_subject"),
        Index("idx_identity_binding_user_id", "user_id"),
    )


class LocalCredential(Base):
    __tablename__ = "local_credential"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128), ForeignKey("user_account.id"), nullable=False)
    username: Mapped[str] = mapped_column(String(64), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    failed_attempts: Mapped[int] = mapped_column(nullable=False, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = created_at()
    updated_at: Mapped[datetime] = updated_at()

    __table_args__ = (
        Index("idx_local_credential_username", "username", unique=True),
        Index("idx_local_credential_user_id", "user_id", unique=True),
    )
