"""Skill search document with tsvector STORED generated column."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Computed, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from skillhub_api.infra.db.base import Base
from skillhub_api.infra.db.models._common import updated_at

# Mirror of the Java V2/V11/V30/V31 tsvector expression. The `simple` config is
# intentional: the Java service tokenizes search text externally via jieba and
# writes the result into `search_text`, so we don't want PostgreSQL to apply
# its own language-specific lemmatization on top.
_SEARCH_VECTOR_EXPR = (
    "setweight(to_tsvector('simple', coalesce(title, '')), 'A') || "
    "setweight(to_tsvector('simple', coalesce(summary, '')), 'B') || "
    "setweight(to_tsvector('simple', coalesce(keywords, '')), 'B') || "
    "setweight(to_tsvector('simple', coalesce(search_text, '')), 'C')"
)


class SkillSearchDocument(Base):
    __tablename__ = "skill_search_document"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    skill_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("skill.id"), nullable=False, unique=True
    )
    namespace_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    namespace_slug: Mapped[str] = mapped_column(String(64), nullable=False)
    owner_id: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    keywords: Mapped[str | None] = mapped_column(Text, nullable=True)
    search_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    semantic_vector: Mapped[str | None] = mapped_column(Text, nullable=True)
    visibility: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    updated_at: Mapped[datetime] = updated_at()
    search_vector = mapped_column(
        TSVECTOR,
        Computed(_SEARCH_VECTOR_EXPR, persisted=True),
    )

    __table_args__ = (
        Index("idx_search_vector", "search_vector", postgresql_using="gin"),
        Index("idx_search_doc_namespace", "namespace_id"),
        Index("idx_search_doc_visibility", "visibility"),
    )
