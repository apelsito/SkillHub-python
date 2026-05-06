"""Skill aggregate: skill, skill_version, skill_file, skill_tag, skill_version_stats."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from skillhub_api.infra.db.base import Base
from skillhub_api.infra.db.models._common import created_at, updated_at


class Skill(Base):
    __tablename__ = "skill"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    namespace_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("namespace.id"), nullable=False
    )
    slug: Mapped[str] = mapped_column(String(128), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("user_account.id"), nullable=False
    )
    source_skill_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    visibility: Mapped[str] = mapped_column(String(32), nullable=False, default="PUBLIC")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACTIVE")
    latest_version_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    download_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    subscription_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    star_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rating_avg: Mapped[Decimal] = mapped_column(
        Numeric(3, 2), nullable=False, server_default=text("0.00")
    )
    rating_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    hidden: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    hidden_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    hidden_by: Mapped[str | None] = mapped_column(
        String(128), ForeignKey("user_account.id"), nullable=True
    )
    created_by: Mapped[str | None] = mapped_column(
        String(128), ForeignKey("user_account.id"), nullable=True
    )
    created_at: Mapped[datetime] = created_at()
    updated_by: Mapped[str | None] = mapped_column(
        String(128), ForeignKey("user_account.id"), nullable=True
    )
    updated_at: Mapped[datetime] = updated_at()

    __table_args__ = (
        UniqueConstraint("namespace_id", "slug", "owner_id", name="uq_skill_namespace_slug_owner"),
        Index("idx_skill_namespace_status", "namespace_id", "status"),
        Index(
            "idx_skill_hidden",
            "hidden",
            postgresql_where=text("hidden = TRUE"),
        ),
        Index(
            "idx_skill_active_visible_updated",
            text("updated_at DESC"),
            text("id DESC"),
            postgresql_where=text("status = 'ACTIVE' AND hidden = FALSE"),
        ),
        Index(
            "idx_skill_active_visible_downloads",
            text("download_count DESC"),
            text("updated_at DESC"),
            text("id DESC"),
            postgresql_where=text("status = 'ACTIVE' AND hidden = FALSE"),
        ),
        Index(
            "idx_skill_active_visible_rating",
            text("rating_avg DESC"),
            text("updated_at DESC"),
            text("id DESC"),
            postgresql_where=text("status = 'ACTIVE' AND hidden = FALSE"),
        ),
    )


class SkillVersion(Base):
    __tablename__ = "skill_version"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    skill_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("skill.id"), nullable=False)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="DRAFT")
    changelog: Mapped[str | None] = mapped_column(Text, nullable=True)
    parsed_metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    manifest_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    file_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_size: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    bundle_ready: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    download_ready: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    requested_visibility: Mapped[str | None] = mapped_column(String(20), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[str | None] = mapped_column(
        String(128), ForeignKey("user_account.id"), nullable=True
    )
    created_at: Mapped[datetime] = created_at()
    yanked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    yanked_by: Mapped[str | None] = mapped_column(
        String(128), ForeignKey("user_account.id"), nullable=True
    )
    yank_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint("skill_id", "version", name="uq_skill_version_skill_version"),
        Index("idx_skill_version_skill_status", "skill_id", "status"),
    )


class SkillFile(Base):
    __tablename__ = "skill_file"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    version_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("skill_version.id"), nullable=False
    )
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    created_at: Mapped[datetime] = created_at()

    __table_args__ = (
        UniqueConstraint("version_id", "file_path", name="uq_skill_file_version_path"),
    )


class SkillTag(Base):
    __tablename__ = "skill_tag"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    skill_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("skill.id"), nullable=False)
    tag_name: Mapped[str] = mapped_column(String(64), nullable=False)
    version_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("skill_version.id"), nullable=False
    )
    created_by: Mapped[str | None] = mapped_column(
        String(128), ForeignKey("user_account.id"), nullable=True
    )
    created_at: Mapped[datetime] = created_at()
    updated_at: Mapped[datetime] = updated_at()

    __table_args__ = (UniqueConstraint("skill_id", "tag_name", name="uq_skill_tag_skill_name"),)


class SkillVersionStats(Base):
    __tablename__ = "skill_version_stats"

    skill_version_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("skill_version.id", ondelete="CASCADE"),
        primary_key=True,
    )
    skill_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("skill.id", ondelete="CASCADE"), nullable=False
    )
    download_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    updated_at: Mapped[datetime] = updated_at()

    __table_args__ = (Index("idx_skill_version_stats_skill_id", "skill_id"),)
