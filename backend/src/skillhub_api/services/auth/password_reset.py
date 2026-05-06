"""Password reset flow.

Mirrors ``PasswordResetService.java``: the request endpoint is always silent
(no user enumeration); a 6-digit numeric code is mailed and BCrypt-hashed in
storage; `PT10M` code expiry is configurable via env.

The email delivery is stubbed here — Phase 6 wires ``aiosmtplib``. Until
then we return the plaintext code in the response only when
``SKILLHUB_AUTH_DIRECT_ENABLED=true`` (useful in local dev).
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from skillhub_api.domain.auth import PASSWORD_RESET_CODE_DIGITS, UserStatus
from skillhub_api.errors import UnauthorizedError
from skillhub_api.infra.repositories.password_reset import PasswordResetRequestRepository
from skillhub_api.infra.repositories.user import LocalCredentialRepository, UserRepository
from skillhub_api.services.auth.passwords import hash_password, verify_password
from skillhub_api.settings import get_settings


def _generate_code() -> str:
    # 6 digits, zero-padded. secrets.randbelow provides CSPRNG output.
    return f"{secrets.randbelow(10**PASSWORD_RESET_CODE_DIGITS):0{PASSWORD_RESET_CODE_DIGITS}d}"


class PasswordResetService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._users = UserRepository(session)
        self._creds = LocalCredentialRepository(session)
        self._requests = PasswordResetRequestRepository(session)

    async def request_reset(self, *, email: str) -> dict[str, Any]:
        """Create a reset request. Returns an opaque response shape; never
        reveals whether the email exists. In direct-auth mode the plaintext
        code is surfaced so local dev doesn't need SMTP.
        """
        settings = get_settings()
        user = await self._users.find_by_email(email)
        if user is None or user.status != UserStatus.ACTIVE.value:
            return {"status": "ok"}

        cred = await self._creds.find_by_user_id(user.id)
        if cred is None:
            # No local credential → nothing to reset; stay silent.
            return {"status": "ok"}

        code = _generate_code()
        expires_at = datetime.now(UTC) + settings.auth.password_reset_code_expiry
        await self._requests.create(
            user_id=user.id,
            email=email,
            code_hash=hash_password(code),
            expires_at=expires_at,
        )

        response: dict[str, Any] = {"status": "ok"}
        if settings.auth.direct_enabled:
            response["debug_code"] = code
            response["debug_expires_at"] = expires_at.isoformat()
        return response

    async def confirm(self, *, email: str, code: str, new_password: str) -> None:
        user = await self._users.find_by_email(email)
        if user is None:
            raise UnauthorizedError("INVALID_RESET_CODE", "invalid or expired code")
        row = await self._requests.latest_pending(user.id)
        if row is None:
            raise UnauthorizedError("INVALID_RESET_CODE", "invalid or expired code")
        if not verify_password(code, row.code_hash):
            raise UnauthorizedError("INVALID_RESET_CODE", "invalid or expired code")

        cred = await self._creds.find_by_user_id(user.id)
        if cred is None:
            raise UnauthorizedError("INVALID_RESET_CODE", "invalid or expired code")

        cred.password_hash = hash_password(new_password)
        cred.failed_attempts = 0
        cred.locked_until = None
        await self._requests.consume(row)
        await self._session.flush()
