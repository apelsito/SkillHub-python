"""Full-text + semantic-blended search.

Ports ``PostgresFullTextQueryService``:

  * tsquery: up to 8 user-typed tokens, ASCII-letter tokens get ``:*``
    prefix matching, CJK/digit tokens do not.
  * Sort orders: ``downloads``, ``rating``, ``newest``, ``relevance``.
    Relevance uses a CASE expression that prioritises exact title match,
    then title prefix, then title substring, then tsrank.
  * Semantic blending: when ``sort=relevance`` and the keyword is
    non-empty, we overfetch by ``candidate_multiplier`` (default 8),
    score each candidate with the cosine similarity of
    ``embed(keyword)`` against the stored ``semantic_vector``, and blend
    ``baseScore * (1 - semantic_weight) + semanticScore * semantic_weight``.

Candidates are bounded by ``max_candidates`` (default 120) to keep the
query bounded regardless of page size.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from skillhub_api.search.embedding import deserialize, embed
from skillhub_api.search.tokenizer import tokenize_for_query
from skillhub_api.settings import get_settings

MAX_QUERY_TERMS = 8
SHORT_PREFIX_LENGTH = 2


def _ts_compatible(token: str) -> bool:
    # Any letter/digit/underscore/ideographic char makes this term usable
    # inside a tsquery. Pure punctuation or whitespace-only terms are dropped.
    return any(ch.isalnum() or ch == "_" for ch in token)


def _is_ascii_letter_token(token: str) -> bool:
    return token.isascii() and all(ch.isalpha() or ch.isdigit() or ch == "_" for ch in token)


def _build_tsquery(keyword: str) -> str | None:
    tokens = tokenize_for_query(keyword)[:MAX_QUERY_TERMS]
    terms: list[str] = []
    for tok in tokens:
        if not _ts_compatible(tok):
            continue
        # Only ASCII alphanumerics get the prefix ``:*`` — CJK already
        # matches via the tokenized ``search_text`` column so the prefix
        # operator would be redundant there.
        if _is_ascii_letter_token(tok):
            terms.append(f"{tok}:*")
        else:
            terms.append(tok)
    if not terms:
        return None
    return " & ".join(terms)


@dataclass(slots=True)
class SearchHit:
    skill_id: int
    namespace_slug: str
    title: str | None
    summary: str | None
    visibility: str
    status: str
    updated_at: Any
    score: float


@dataclass(slots=True)
class SearchPage:
    items: list[SearchHit]
    total: int
    limit: int
    offset: int


_BASE_SELECT_COLUMNS = (
    "d.skill_id, d.namespace_slug, d.title, d.summary, d.visibility, "
    "d.status, d.updated_at, s.download_count, s.rating_avg"
)

_ORDER_BY = {
    "downloads": "s.download_count DESC, s.updated_at DESC, d.skill_id DESC",
    "rating": "s.rating_avg DESC, s.updated_at DESC, d.skill_id DESC",
    "newest": "s.updated_at DESC, d.skill_id DESC",
}


class SearchQueryService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def search(
        self,
        *,
        keyword: str | None,
        namespace: str | None,
        sort: str,
        limit: int,
        offset: int,
    ) -> SearchPage:
        settings = get_settings()
        sort = sort if sort in {"downloads", "rating", "newest", "relevance"} else "newest"

        params: dict[str, Any] = {"limit": limit, "offset": offset}
        where_parts = [
            "d.status = 'ACTIVE'",
            "s.status = 'ACTIVE'",
            "s.hidden = FALSE",
            "d.visibility = 'PUBLIC'",
        ]
        if namespace:
            where_parts.append("d.namespace_slug = :namespace")
            params["namespace"] = namespace

        tsquery_str: str | None = None
        if keyword:
            tsquery_str = _build_tsquery(keyword)
            if tsquery_str:
                where_parts.append("d.search_vector @@ to_tsquery('simple', :tsq)")
                params["tsq"] = tsquery_str

        where_clause = " AND ".join(where_parts)

        # Relevance sort needs extra columns (rank + title match) to compute
        # the CASE. Other sorts use the shared ORDER BY constant.
        if sort == "relevance" and tsquery_str is not None:
            return await self._relevance_search(
                keyword=keyword or "",
                where_clause=where_clause,
                base_params=params,
                limit=limit,
                offset=offset,
                semantic_enabled=settings.search.semantic_enabled,
                semantic_weight=settings.search.semantic_weight,
                candidate_multiplier=settings.search.semantic_candidate_multiplier,
                max_candidates=settings.search.semantic_max_candidates,
            )

        order_by = _ORDER_BY.get(sort, _ORDER_BY["newest"])
        list_sql = text(
            f"""
            SELECT {_BASE_SELECT_COLUMNS}
            FROM skill_search_document d
            JOIN skill s ON s.id = d.skill_id
            WHERE {where_clause}
            ORDER BY {order_by}
            LIMIT :limit OFFSET :offset
            """
        )
        count_sql = text(
            f"""
            SELECT COUNT(*) FROM skill_search_document d
            JOIN skill s ON s.id = d.skill_id
            WHERE {where_clause}
            """
        )
        rows = (await self._session.execute(list_sql, params)).mappings().all()
        total = (await self._session.execute(count_sql, params)).scalar_one()
        hits = [
            SearchHit(
                skill_id=r["skill_id"],
                namespace_slug=r["namespace_slug"],
                title=r["title"],
                summary=r["summary"],
                visibility=r["visibility"],
                status=r["status"],
                updated_at=r["updated_at"],
                score=0.0,
            )
            for r in rows
        ]
        return SearchPage(items=hits, total=int(total), limit=limit, offset=offset)

    async def _relevance_search(
        self,
        *,
        keyword: str,
        where_clause: str,
        base_params: dict[str, Any],
        limit: int,
        offset: int,
        semantic_enabled: bool,
        semantic_weight: float,
        candidate_multiplier: int,
        max_candidates: int,
    ) -> SearchPage:
        # Overfetch so semantic reranking has headroom.
        candidates = min(max_candidates, max(limit * candidate_multiplier, limit + offset))

        list_sql = text(
            f"""
            SELECT {_BASE_SELECT_COLUMNS}, d.semantic_vector,
                   ts_rank_cd(d.search_vector, to_tsquery('simple', :tsq)) AS rank,
                   CASE
                     WHEN lower(d.title) = lower(:kw_exact)       THEN 4
                     WHEN lower(d.title) LIKE lower(:kw_prefix)    THEN 3
                     WHEN lower(d.title) LIKE lower(:kw_contains)  THEN 2
                     ELSE 1
                   END AS match_kind
            FROM skill_search_document d
            JOIN skill s ON s.id = d.skill_id
            WHERE {where_clause}
            ORDER BY match_kind DESC,
                     ts_rank_cd(d.search_vector, to_tsquery('simple', :tsq)) DESC,
                     s.download_count DESC,
                     s.updated_at DESC,
                     d.skill_id DESC
            LIMIT :candidates
            """
        )
        count_sql = text(
            f"""
            SELECT COUNT(*) FROM skill_search_document d
            JOIN skill s ON s.id = d.skill_id
            WHERE {where_clause}
            """
        )
        params = {
            **base_params,
            "kw_exact": keyword,
            "kw_prefix": f"{keyword}%",
            "kw_contains": f"%{keyword}%",
            "candidates": candidates,
        }

        rows = (await self._session.execute(list_sql, params)).mappings().all()
        total = int((await self._session.execute(count_sql, params)).scalar_one())

        if not rows:
            return SearchPage(items=[], total=total, limit=limit, offset=offset)

        # Compute blended score. baseScore for rank i is (1 - i/N) so the
        # top candidate gets 1.0 and the last gets ~0.
        n = len(rows)
        query_vec = deserialize(embed(keyword)) if semantic_enabled else None

        scored: list[tuple[float, SearchHit]] = []
        for i, r in enumerate(rows):
            base_score = 1.0 - (i / n)
            semantic_score = 0.0
            if query_vec is not None and r["semantic_vector"]:
                doc_vec = deserialize(r["semantic_vector"])
                if len(doc_vec) == len(query_vec):
                    semantic_score = sum(a * b for a, b in zip(query_vec, doc_vec, strict=True))
            combined = base_score * (1 - semantic_weight) + semantic_score * semantic_weight
            hit = SearchHit(
                skill_id=r["skill_id"],
                namespace_slug=r["namespace_slug"],
                title=r["title"],
                summary=r["summary"],
                visibility=r["visibility"],
                status=r["status"],
                updated_at=r["updated_at"],
                score=combined,
            )
            scored.append((combined, hit))

        scored.sort(key=lambda pair: pair[0], reverse=True)
        paginated = scored[offset : offset + limit]
        return SearchPage(
            items=[h for _, h in paginated],
            total=total,
            limit=limit,
            offset=offset,
        )
