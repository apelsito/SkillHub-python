"""Audit log."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from skillhub_api.infra.db.base import Base
from skillhub_api.infra.db.models._common import created_at


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    actor_user_id: Mapped[str | None] = mapped_column(
        String(128), ForeignKey("user_account.id"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    target_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    client_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    detail_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = created_at()

    __table_args__ = (
        Index("idx_audit_log_actor", "actor_user_id"),
        Index("idx_audit_log_created_at", "created_at"),
        Index("idx_audit_log_request_id", "request_id"),
        Index("idx_audit_log_actor_time", "actor_user_id", text("created_at DESC")),
        Index("idx_audit_log_action_time", "action", text("created_at DESC")),
    )
