"""Tokenizer compatible with the Java SkillHub search pipeline.

Ports ``SearchTextTokenizer.java``:
  * INDEX mode for indexing (``jieba.cut_for_search``-equivalent → use
    ``jieba.cut_for_search()`` which emits fine-grained tokens ideal for
    index population).
  * SEARCH mode for querying (``jieba.cut(..., HMM=True)`` — coarser
    tokens, closer to what a user types).
  * ASCII tokens are lowercased; CJK tokens keep their case (no practical
    difference, but we keep the rule for fidelity).
  * No stopwords, no min-length filter, no NFC normalization (matches
    Java exactly).
  * Whitespace is collapsed to single spaces.

Jieba's Python port (``fxsjy/jieba``) and the Java port
(``com.huaban.jieba-analysis``) share the same dictionary lineage, but
tokenization can drift on edge cases (mixed CJK+ASCII, custom dicts). No
known production divergence today; see §6 of the plan for the mitigation
path (golden-file tests + optional JVM sidecar).
"""

from __future__ import annotations

import re
from enum import StrEnum

import jieba

_ASCII_RE = re.compile(r"^[\x00-\x7f]+$")
_WS_RE = re.compile(r"\s+")


class Mode(StrEnum):
    INDEX = "INDEX"
    SEARCH = "SEARCH"


def _normalize(text: str) -> str | None:
    if text is None:
        return None
    stripped = _WS_RE.sub(" ", text).strip()
    return stripped or None


def _normalize_token(token: str) -> str | None:
    t = token.strip()
    if not t:
        return None
    if _ASCII_RE.match(t):
        return t.lower()
    return t


def tokenize(text: str, mode: Mode) -> list[str]:
    """Return a deduplicated, order-preserving list of tokens."""
    source = _normalize(text)
    if source is None:
        return []
    raw_iter = jieba.cut_for_search(source) if mode == Mode.INDEX else jieba.cut(source, HMM=True)

    seen: dict[str, None] = {}
    for raw in raw_iter:
        normalized = _normalize_token(raw)
        if normalized is None:
            continue
        seen[normalized] = None
    return list(seen)


def tokenize_for_index(text: str) -> list[str]:
    return tokenize(text, Mode.INDEX)


def tokenize_for_query(text: str) -> list[str]:
    return tokenize(text, Mode.SEARCH)


def enrich_for_index(raw_text: str) -> str:
    """Return the raw text plus space-joined index tokens.

    Mirrors ``enrichForIndex()`` in Java: the index stores both the
    original string and the tokenized form, so tsvector weights pick up
    both exact and tokenized matches.
    """
    normalized = _normalize(raw_text)
    if normalized is None:
        return ""
    tokens = tokenize(normalized, Mode.INDEX)
    return " ".join([normalized, *tokens])
