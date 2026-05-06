from skillhub_api.search.tokenizer import (
    Mode,
    enrich_for_index,
    tokenize,
    tokenize_for_index,
    tokenize_for_query,
)


def test_empty_input_returns_empty_list() -> None:
    assert tokenize("", Mode.INDEX) == []
    assert tokenize("   ", Mode.INDEX) == []


def test_ascii_tokens_lowercase() -> None:
    tokens = tokenize_for_index("Hello World")
    assert "hello" in tokens
    assert "world" in tokens
    assert not any(t != t.lower() for t in tokens if t.isascii())


def test_whitespace_collapsed_preserving_content() -> None:
    tokens = tokenize_for_index("  Hello   World  ")
    assert "hello" in tokens and "world" in tokens


def test_tokens_deduplicated() -> None:
    tokens = tokenize_for_index("hello hello world")
    assert tokens.count("hello") == 1


def test_query_and_index_both_produce_tokens() -> None:
    assert len(tokenize_for_query("hello world")) >= 2
    assert len(tokenize_for_index("hello world")) >= 2


def test_enrich_for_index_prepends_normalized_text() -> None:
    enriched = enrich_for_index("Hello   World")
    # Single-space normalized original comes first.
    assert enriched.startswith("Hello World")
    # Tokens follow (lowercased).
    assert "hello" in enriched
    assert "world" in enriched


def test_enrich_empty_returns_empty_string() -> None:
    assert enrich_for_index("") == ""
    assert enrich_for_index("   ") == ""


def test_index_tokenizer_segments_ascii_words() -> None:
    tokens = tokenize_for_index("hello world")

    assert tokens == ["hello", "world"]
