"""API token generation + hashing.

Mirrors the Java ``ApiTokenService`` contract:
  * plaintext format: ``sk_<base64url(32 random bytes, no padding)>``
  * ``token_prefix`` = first 8 characters of the plaintext (stored for UI display)
  * ``token_hash`` = uppercase SHA-256 hex of the plaintext (stored for lookup)

The plaintext is only returned once at creation time; after that, only the
prefix + hash are persisted, so a leaked DB cannot recover the token.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
from dataclasses import dataclass

TOKEN_PREFIX = "sk_"
PREFIX_STORAGE_LENGTH = 8
RANDOM_BYTES = 32


@dataclass(frozen=True, slots=True)
class GeneratedToken:
    plaintext: str
    prefix: str
    hash_hex: str


def generate_token() -> GeneratedToken:
    raw = secrets.token_bytes(RANDOM_BYTES)
    body = base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")
    plaintext = TOKEN_PREFIX + body
    prefix = plaintext[:PREFIX_STORAGE_LENGTH]
    hash_hex = hashlib.sha256(plaintext.encode("ascii")).hexdigest().upper()
    return GeneratedToken(plaintext=plaintext, prefix=prefix, hash_hex=hash_hex)


def hash_token(plaintext: str) -> str:
    """Reproduce the stored hash for a given plaintext token."""
    return hashlib.sha256(plaintext.encode("ascii")).hexdigest().upper()
