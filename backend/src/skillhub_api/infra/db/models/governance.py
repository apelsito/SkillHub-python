"""Governance: review_task, promotion_request, skill_report."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from skillhub_api.infra.db.base import Base
from skillhub_api.infra.db.models._common import created_at


class ReviewTask(Base):
    __tablename__ = "review_task"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    skill_version_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("skill_version.id"), nullable=False
    )
    namespace_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("namespace.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    submitted_by: Mapped[str] = mapped_column(
        String(128), ForeignKey("user_account.id"), nullable=False
    )
    reviewed_by: Mapped[str | None] = mapped_column(
        String(128), ForeignKey("user_account.id"), nullable=True
    )
    review_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    submitted_at: Mapped[datetime] = created_at()
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("idx_review_task_namespace_status", "namespace_id", "status"),
        Index("idx_review_task_submitted_by_status", "submitted_by", "status"),
        Index(
            "idx_review_task_version_pending",
            "skill_version_id",
            unique=True,
            postgresql_where=text("status = 'PENDING'"),
        ),
    )


class PromotionRequest(Base):
    __tablename__ = "promotion_request"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source_skill_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("skill.id"), nullable=False)
    source_version_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("skill_version.id"), nullable=False
    )
    target_namespace_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("namespace.id"), nullable=False
    )
    target_skill_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("skill.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    submitted_by: Mapped[str] = mapped_column(
        String(128), ForeignKey("user_account.id"), nullable=False
    )
    reviewed_by: Mapped[str | None] = mapped_column(
        String(128), ForeignKey("user_account.id"), nullable=True
    )
    review_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    submitted_at: Mapped[datetime] = created_at()
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("idx_promotion_request_source_skill", "source_skill_id"),
        Index("idx_promotion_request_status", "status"),
        Index(
            "idx_promotion_request_version_pending",
            "source_version_id",
            unique=True,
            postgresql_where=text("status = 'PENDING'"),
        ),
    )


class SkillReport(Base):
    __tablename__ = "skill_report"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    skill_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("skill.id", ondelete="CASCADE"), nullable=False
    )
    namespace_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("namespace.id", ondelete="CASCADE"), nullable=False
    )
    reporter_id: Mapped[str] = mapped_column(String(128), nullable=False)
    reason: Mapped[str] = mapped_column(String(200), nullable=False)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    handled_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    handle_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = created_at()
    handled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index(
            "idx_skill_report_status_created_at",
            "status",
            text("created_at DESC"),
        ),
        Index("idx_skill_report_skill_id", "skill_id"),
    )
