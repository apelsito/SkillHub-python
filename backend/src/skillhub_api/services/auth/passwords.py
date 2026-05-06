"""Password hashing — bcrypt with cost factor 12.

Matches the Java Spring Security ``BCryptPasswordEncoder(12)`` config at
``server/skillhub-auth/src/main/java/com/iflytek/skillhub/auth/config/SecurityConfig.java:173``.
Using the same algorithm + cost means passwords created by either backend
validate on both — important during any cutover window.
"""

from __future__ import annotations

from passlib.context import CryptContext

_BCRYPT_ROUNDS = 12

_pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=_BCRYPT_ROUNDS,
)


def hash_password(plain: str) -> str:
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _pwd_context.verify(plain, hashed)
    except (ValueError, TypeError):
        return False
