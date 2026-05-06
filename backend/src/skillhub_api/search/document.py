"""Build a ``SkillSearchDocument`` from a ``Skill`` + its latest version.

Mirrors the Java ``buildDocument()`` helper:
  * ``search_text`` = enriched concatenation of slug + summary + any
    extra frontmatter fields.
  * ``keywords`` = enriched concatenation of tag fields pulled from the
    manifest (keyword, keywords, tag, tags).
  * ``semantic_vector`` = embedding of ``title\\nsummary\\nkeywords\\nsearch_text``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from skillhub_api.search.embedding import embed
from skillhub_api.search.tokenizer import enrich_for_index

_KEYWORD_KEY_RE = re.compile(r"^(keyword|keywords|tag|tags)$", re.IGNORECASE)
_RESERVED_FRONTMATTER = frozenset({"name", "description", "version"})


@dataclass(slots=True)
class SkillSearchDocumentInput:
    skill_id: int
    namespace_id: int
    namespace_slug: str
    owner_id: str
    title: str | None
    summary: str | None
    keywords: str | None
    search_text: str | None
    semantic_vector: str | None
    visibility: str
    status: str


def _scalar(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, int | float | bool):
        return str(value)
    if isinstance(value, list | tuple):
        return " ".join(s for v in value if (s := _scalar(v)))
    return None


def _extract_keywords(frontmatter: dict[str, Any]) -> str:
    parts: list[str] = []
    for key, value in frontmatter.items():
        if _KEYWORD_KEY_RE.match(str(key)):
            scalar = _scalar(value)
            if scalar:
                parts.append(scalar)
    return " ".join(parts)


def _extract_search_text(
    slug: str,
    summary: str | None,
    frontmatter: dict[str, Any],
) -> str:
    parts: list[str] = [slug]
    if summary:
        parts.append(summary)
    for key, value in frontmatter.items():
        if str(key).lower() in _RESERVED_FRONTMATTER:
            continue
        if _KEYWORD_KEY_RE.match(str(key)):
            continue
        scalar = _scalar(value)
        if scalar:
            parts.append(scalar)
    return " ".join(parts)


def build_document(
    *,
    skill_id: int,
    namespace_id: int,
    namespace_slug: str,
    owner_id: str,
    slug: str,
    display_name: str | None,
    summary: str | None,
    visibility: str,
    status: str,
    manifest: dict[str, Any] | None,
) -> SkillSearchDocumentInput:
    fm = manifest or {}
    title = display_name or ""
    keywords_raw = _extract_keywords(fm)
    search_raw = _extract_search_text(slug, summary, fm)

    keywords = enrich_for_index(keywords_raw) if keywords_raw else ""
    search_text = enrich_for_index(search_raw) if search_raw else ""

    semantic_source = "\n".join([title, summary or "", keywords or "", search_text or ""])
    semantic_vector = embed(semantic_source) if semantic_source.strip() else None

    return SkillSearchDocumentInput(
        skill_id=skill_id,
        namespace_id=namespace_id,
        namespace_slug=namespace_slug,
        owner_id=owner_id,
        title=title[:512] if title else None,
        summary=summary,
        keywords=keywords or None,
        search_text=search_text or None,
        semantic_vector=semantic_vector,
        visibility=visibility,
        status=status,
    )
