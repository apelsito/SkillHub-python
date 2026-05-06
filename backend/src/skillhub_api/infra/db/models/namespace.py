"""Namespace + member tables."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from skillhub_api.infra.db.base import Base
from skillhub_api.infra.db.models._common import created_at, updated_at


class Namespace(Base):
    __tablename__ = "namespace"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACTIVE")
    created_by: Mapped[str | None] = mapped_column(
        String(128), ForeignKey("user_account.id"), nullable=True
    )
    created_at: Mapped[datetime] = created_at()
    updated_at: Mapped[datetime] = updated_at()


class NamespaceMember(Base):
    __tablename__ = "namespace_member"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    namespace_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("namespace.id"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(String(128), ForeignKey("user_account.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = created_at()
    updated_at: Mapped[datetime] = updated_at()

    __table_args__ = (
        UniqueConstraint("namespace_id", "user_id", name="uq_namespace_member_namespace_user"),
        Index("idx_namespace_member_user_id", "user_id"),
        Index("idx_namespace_member_namespace_id", "namespace_id"),
    )
