import math

import pytest

from skillhub_api.search.embedding import (
    DIMENSIONS,
    NGRAM_WEIGHT,
    _tokens,
    deserialize,
    embed,
    similarity,
)


def test_empty_text_produces_zero_vector() -> None:
    serialized = embed("")
    parts = serialized.split(",")
    assert len(parts) == DIMENSIONS
    assert all(p == "0.000000" for p in parts)


def test_embedding_is_l2_normalized() -> None:
    serialized = embed("hello world")
    vec = [float(p) for p in serialized.split(",")]
    norm = math.sqrt(sum(v * v for v in vec))
    # L2 norm of a non-zero embedding should be ~1.
    assert norm == pytest.approx(1.0, rel=1e-5)


def test_embedding_is_deterministic() -> None:
    assert embed("hello world") == embed("hello world")
    assert embed("HELLO WORLD") == embed("hello world")  # lowercased


def test_embedding_serialization_format() -> None:
    serialized = embed("hello")
    parts = serialized.split(",")
    assert len(parts) == DIMENSIONS
    for p in parts:
        # Each float must be 6-decimal formatted (potentially with a minus sign).
        assert "." in p
        assert len(p.split(".")[1]) == 6


def test_similarity_of_identical_text_is_one() -> None:
    s = similarity("hello world", embed("hello world"))
    assert s == pytest.approx(1.0, rel=1e-5)


def test_similarity_of_different_text_is_less_than_one() -> None:
    s = similarity("hello world", embed("completely different phrase here"))
    assert s < 0.9


def test_tokens_splits_on_non_word_characters() -> None:
    assert _tokens("hello-world_42") == ["hello", "world_42"]
    assert _tokens("!!!") == []
    assert _tokens("foo.bar,baz") == ["foo", "bar", "baz"]


def test_deserialize_reapplies_l2_normalization() -> None:
    # A hand-rolled un-normalized vector should come back normalized.
    raw = ",".join([f"{x:.6f}" for x in [1.0, 2.0] + [0.0] * (DIMENSIONS - 2)])
    deserialized = deserialize(raw)
    assert math.sqrt(sum(v * v for v in deserialized)) == pytest.approx(1.0, rel=1e-5)


def test_ngram_weight_constant_matches_java() -> None:
    assert NGRAM_WEIGHT == 0.35
    assert DIMENSIONS == 64
