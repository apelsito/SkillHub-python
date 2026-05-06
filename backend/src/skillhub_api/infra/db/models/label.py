"""Label system (V34): label_definition, label_translation, skill_label."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from skillhub_api.infra.db.base import Base
from skillhub_api.infra.db.models._common import created_at, updated_at


class LabelDefinition(Base):
    __tablename__ = "label_definition"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    visible_in_filter: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_by: Mapped[str | None] = mapped_column(
        String(128), ForeignKey("user_account.id"), nullable=True
    )
    created_at: Mapped[datetime] = created_at()
    updated_at: Mapped[datetime] = updated_at()

    __table_args__ = (
        CheckConstraint(
            "type IN ('RECOMMENDED', 'PRIVILEGED')", name="label_definition_type_check"
        ),
        Index(
            "idx_label_definition_visible_sort",
            "visible_in_filter",
            "type",
            "sort_order",
            "id",
        ),
    )


class LabelTranslation(Base):
    __tablename__ = "label_translation"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    label_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("label_definition.id", ondelete="CASCADE"),
        nullable=False,
    )
    locale: Mapped[str] = mapped_column(String(16), nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = created_at()
    updated_at: Mapped[datetime] = updated_at()

    __table_args__ = (
        UniqueConstraint("label_id", "locale", name="uq_label_translation_label_locale"),
        Index("idx_label_translation_label_id", "label_id"),
    )


class SkillLabel(Base):
    __tablename__ = "skill_label"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    skill_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("skill.id", ondelete="CASCADE"), nullable=False
    )
    label_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("label_definition.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_by: Mapped[str | None] = mapped_column(
        String(128), ForeignKey("user_account.id"), nullable=True
    )
    created_at: Mapped[datetime] = created_at()

    __table_args__ = (
        UniqueConstraint("skill_id", "label_id", name="uq_skill_label_skill_label"),
        Index("idx_skill_label_label_id", "label_id"),
        Index("idx_skill_label_skill_id", "skill_id"),
    )
