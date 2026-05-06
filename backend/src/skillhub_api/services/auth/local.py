"""Local username/password auth service.

Ports ``LocalAuthService.java``:
  * username regex ``^[A-Za-z0-9_]{3,64}$``
  * 5 failed attempts → 15-minute lockout via ``locked_until``
  * only ACTIVE users can log in (PENDING/DISABLED/MERGED rejected)
  * bcrypt(12) for passwords

User IDs follow Java's convention: a stable hex string (we use a UUID4 hex so
it fits the ``VARCHAR(128)`` column).
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from skillhub_api.domain.auth import (
    LOCKOUT_MINUTES,
    MAX_FAILED_ATTEMPTS,
    USERNAME_PATTERN,
    UserStatus,
)
from skillhub_api.errors import ConflictError, ForbiddenError, UnauthorizedError
from skillhub_api.infra.db.models.user import LocalCredential, UserAccount
from skillhub_api.infra.repositories.user import (
    LocalCredentialRepository,
    UserRepository,
)
from skillhub_api.services.auth.passwords import hash_password, verify_password

_USERNAME_RE = re.compile(USERNAME_PATTERN)


def _utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class LocalAuthService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._users = UserRepository(session)
        self._creds = LocalCredentialRepository(session)

    async def register(
        self,
        *,
        username: str,
        password: str,
        email: str | None,
        display_name: str | None = None,
    ) -> UserAccount:
        if not _USERNAME_RE.match(username):
            raise ConflictError(
                "INVALID_USERNAME",
                "username must match [A-Za-z0-9_]{3,64}",
            )
        if await self._creds.find_by_username(username):
            raise ConflictError("USERNAME_TAKEN", "username already in use")
        if email and await self._users.find_by_email(email):
            raise ConflictError("EMAIL_TAKEN", "email already in use")

        user_id = uuid.uuid4().hex
        user = await self._users.create(
            user_id=user_id,
            display_name=display_name or username,
            email=email,
        )
        await self._creds.create(
            user_id=user.id,
            username=username,
            password_hash=hash_password(password),
        )
        return user

    async def login(self, *, username: str, password: str) -> UserAccount:
        cred = await self._creds.find_by_username(username)
        # Constant-time-ish: if the credential is missing, still do a dummy
        # bcrypt verify to avoid leaking username existence via timing. Since
        # we're already raising a generic error, the extra cost is small and
        # matches the Java service's behavior.
        if cred is None:
            verify_password(
                password, "$2b$12$abcdefghijklmnopqrstuvwxyz012345678901234567890123456"
            )
            raise UnauthorizedError("INVALID_CREDENTIALS", "invalid username or password")

        if self._is_locked(cred):
            raise ForbiddenError(
                "ACCOUNT_LOCKED",
                "too many failed attempts — try again later",
            )

        if not verify_password(password, cred.password_hash):
            cred.failed_attempts += 1
            if cred.failed_attempts >= MAX_FAILED_ATTEMPTS:
                cred.locked_until = _utcnow_naive() + timedelta(minutes=LOCKOUT_MINUTES)
            await self._session.flush()
            raise UnauthorizedError("INVALID_CREDENTIALS", "invalid username or password")

        user = await self._users.get(cred.user_id)
        if user is None:
            raise UnauthorizedError("INVALID_CREDENTIALS", "invalid username or password")
        self._assert_active(user)

        # Successful login clears the failure counter.
        if cred.failed_attempts or cred.locked_until:
            cred.failed_attempts = 0
            cred.locked_until = None
            await self._session.flush()
        return user

    async def change_password(
        self,
        *,
        user_id: str,
        current_password: str,
        new_password: str,
    ) -> None:
        cred = await self._creds.find_by_user_id(user_id)
        if cred is None:
            raise UnauthorizedError("INVALID_CREDENTIALS", "no local credential on account")
        if not verify_password(current_password, cred.password_hash):
            raise UnauthorizedError("INVALID_CREDENTIALS", "current password does not match")
        cred.password_hash = hash_password(new_password)
        cred.failed_attempts = 0
        cred.locked_until = None
        await self._session.flush()

    @staticmethod
    def _is_locked(cred: LocalCredential) -> bool:
        if cred.locked_until is None:
            return False
        if cred.locked_until.tzinfo is None:
            return cred.locked_until > _utcnow_naive()
        return cred.locked_until > datetime.now(UTC)

    @staticmethod
    def _assert_active(user: UserAccount) -> None:
        if user.status != UserStatus.ACTIVE.value:
            raise ForbiddenError("ACCOUNT_NOT_ACTIVE", f"account status is {user.status}")
