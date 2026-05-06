"""Security audit records (V35, V36, V38)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Double, Index, Integer, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from skillhub_api.infra.db.base import Base
from skillhub_api.infra.db.models._common import created_at


class SecurityAudit(Base):
    __tablename__ = "security_audit"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    skill_version_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    scan_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    scanner_type: Mapped[str] = mapped_column(String(50), nullable=False, default="skill-scanner")
    verdict: Mapped[str] = mapped_column(String(20), nullable=False)
    is_safe: Mapped[bool] = mapped_column(Boolean, nullable=False)
    max_severity: Mapped[str | None] = mapped_column(String(20), nullable=True)
    findings_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    findings: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    scan_duration_seconds: Mapped[float | None] = mapped_column(Double, nullable=True)
    scanned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = created_at()
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index(
            "idx_security_audit_version_active",
            "skill_version_id",
            "deleted_at",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("idx_security_audit_verdict", "verdict"),
        Index(
            "idx_security_audit_version_type_latest",
            "skill_version_id",
            "scanner_type",
            text("created_at DESC"),
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )
