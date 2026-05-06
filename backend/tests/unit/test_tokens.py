from skillhub_api.services.auth.tokens import (
    PREFIX_STORAGE_LENGTH,
    TOKEN_PREFIX,
    generate_token,
    hash_token,
)


def test_generate_token_shape() -> None:
    t = generate_token()
    assert t.plaintext.startswith(TOKEN_PREFIX)
    assert len(t.prefix) == PREFIX_STORAGE_LENGTH
    assert t.prefix == t.plaintext[:PREFIX_STORAGE_LENGTH]
    assert len(t.hash_hex) == 64
    assert t.hash_hex == t.hash_hex.upper()
    assert t.hash_hex == hash_token(t.plaintext)


def test_generated_tokens_are_unique() -> None:
    seen = {generate_token().plaintext for _ in range(50)}
    assert len(seen) == 50


def test_hash_is_stable() -> None:
    assert hash_token("sk_deadbeef") == hash_token("sk_deadbeef")
    assert hash_token("sk_deadbeef") != hash_token("sk_other")
