"""Idempotency records."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from skillhub_api.infra.db.base import Base
from skillhub_api.infra.db.models._common import created_at


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_record"

    request_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    response_status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = created_at()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("idx_idempotency_record_expires_at", "expires_at"),
        Index("idx_idempotency_record_status_created", "status", "created_at"),
    )
