"""Social: skill_star, skill_rating, skill_subscription."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from skillhub_api.infra.db.base import Base
from skillhub_api.infra.db.models._common import created_at, updated_at


class SkillStar(Base):
    __tablename__ = "skill_star"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    skill_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("skill.id"), nullable=False)
    user_id: Mapped[str] = mapped_column(String(128), ForeignKey("user_account.id"), nullable=False)
    created_at: Mapped[datetime] = created_at()

    __table_args__ = (
        UniqueConstraint("skill_id", "user_id", name="uq_skill_star_skill_user"),
        Index("idx_skill_star_user_id", "user_id"),
        Index("idx_skill_star_skill_id", "skill_id"),
    )


class SkillRating(Base):
    __tablename__ = "skill_rating"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    skill_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("skill.id"), nullable=False)
    user_id: Mapped[str] = mapped_column(String(128), ForeignKey("user_account.id"), nullable=False)
    score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    created_at: Mapped[datetime] = created_at()
    updated_at: Mapped[datetime] = updated_at()

    __table_args__ = (
        CheckConstraint("score >= 1 AND score <= 5", name="skill_rating_score_check"),
        UniqueConstraint("skill_id", "user_id", name="uq_skill_rating_skill_user"),
        Index("idx_skill_rating_skill_id", "skill_id"),
    )


class SkillSubscription(Base):
    __tablename__ = "skill_subscription"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    skill_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("skill.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=text("now()"))

    __table_args__ = (
        UniqueConstraint("skill_id", "user_id", name="uk_skill_subscription"),
        Index("idx_skill_subscription_user", "user_id", text("created_at DESC")),
        Index("idx_skill_subscription_skill", "skill_id"),
    )
