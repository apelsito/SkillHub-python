"""Hashing-based search embedding.

Bit-for-bit port of ``HashingSearchEmbeddingService.java``:

  * 64-dimensional float64 vector.
  * Tokenizer: regex ``[^\\p{L}\\p{N}_]+`` → split, lowercased.
  * Unigram weight: ``1.0 + min(len, 12) / 12.0``.
  * Trigram weight: ``0.35`` for every 3-character sliding-window
    substring of each token (only when ``len(token) >= 3``).
  * Bucket: ``Math.floorMod(token.hashCode(), 64)`` — using
    ``java_string_hashcode`` so the index matches Java's.
  * L2-normalized and serialized as ``"%.6f,%.6f,..."``.

Vectors written by this module round-trip with vectors written by the
Java service — the bucket math is identical.
"""

from __future__ import annotations

import math
import re

from skillhub_api.search.java_hash import java_floor_mod, java_string_hashcode

DIMENSIONS = 64
NGRAM_WEIGHT = 0.35
NGRAM_MIN_TOKEN_LEN = 3
NGRAM_LEN = 3

# Java: ``[^\\p{L}\\p{N}_]+`` — split on any char that is NOT a letter,
# digit, or underscore. Python's ``re`` supports Unicode property
# shortcuts via ``\w`` (letters + digits + underscore). The inverse of
# ``\w`` is exactly the Java intent.
_TOKEN_SPLITTER = re.compile(r"[^\w]+", re.UNICODE)


def _tokens(text: str) -> list[str]:
    if not text:
        return []
    return [t for t in _TOKEN_SPLITTER.split(text.lower()) if t]


def _bucket(token: str) -> int:
    return java_floor_mod(java_string_hashcode(token), DIMENSIONS)


def _unigram_weight(token: str) -> float:
    return 1.0 + min(len(token), 12) / 12.0


def _add_vector(vector: list[float], token: str, weight: float) -> None:
    vector[_bucket(token)] += weight


def _l2_normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vector))
    if norm == 0.0:
        return vector
    return [v / norm for v in vector]


def embed(text: str) -> str:
    """Return the serialized, L2-normalized embedding for ``text``."""
    vector = [0.0] * DIMENSIONS
    for token in _tokens(text):
        _add_vector(vector, token, _unigram_weight(token))
        if len(token) >= NGRAM_MIN_TOKEN_LEN:
            for i in range(len(token) - NGRAM_LEN + 1):
                trigram = token[i : i + NGRAM_LEN]
                _add_vector(vector, trigram, NGRAM_WEIGHT)
    vector = _l2_normalize(vector)
    return ",".join(f"{v:.6f}" for v in vector)


def deserialize(serialized: str) -> list[float]:
    """Parse a stored vector and re-normalize (Java does this on read)."""
    parts = serialized.split(",")
    vector = [float(p) for p in parts]
    return _l2_normalize(vector)


def similarity(query_text: str, stored_vector: str) -> float:
    """Cosine similarity of a freshly-embedded query vs a stored vector.

    Since both vectors are L2-normalized, dot product equals cosine.
    """
    query_vec = deserialize(embed(query_text))
    doc_vec = deserialize(stored_vector)
    if len(query_vec) != len(doc_vec):
        return 0.0
    return sum(q * d for q, d in zip(query_vec, doc_vec, strict=True))
