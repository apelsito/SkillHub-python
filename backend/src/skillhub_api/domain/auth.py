"""Auth domain constants + enums.

Single source of truth for values that must stay byte-identical between the
Java backend and this Python port (status strings, lockout thresholds, role
codes). Changing any of these is a contract break.
"""

from __future__ import annotations

from enum import StrEnum


class UserStatus(StrEnum):
    ACTIVE = "ACTIVE"
    PENDING = "PENDING"
    DISABLED = "DISABLED"
    MERGED = "MERGED"


class TokenStatus(StrEnum):
    ACTIVE = "ACTIVE"
    REVOKED = "REVOKED"
    EXPIRED = "EXPIRED"


# LocalAuthService.java:33-34 — five failures, fifteen minutes.
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 15

# PasswordResetService.java:33 — six numeric digits.
PASSWORD_RESET_CODE_DIGITS = 6

# System role codes seeded in the initial Alembic revision.
ROLE_SUPER_ADMIN = "SUPER_ADMIN"
ROLE_SKILL_ADMIN = "SKILL_ADMIN"
ROLE_USER_ADMIN = "USER_ADMIN"
ROLE_AUDITOR = "AUDITOR"

# Username regex from LocalRegisterRequest.
USERNAME_PATTERN = r"^[A-Za-z0-9_]{3,64}$"
