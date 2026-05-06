"""Bootstrap admin — runs on app startup when enabled.

Mirrors Spring's ``BootstrapAdminService`` intent: if ``BOOTSTRAP_ADMIN_ENABLED=true``
and the configured user does not yet exist, create one with local credentials
and bind the SUPER_ADMIN role. Idempotent: running twice is a no-op.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from skillhub_api.domain.auth import ROLE_SUPER_ADMIN
from skillhub_api.infra.db.models.user import LocalCredential, UserAccount
from skillhub_api.infra.repositories.role import RoleRepository
from skillhub_api.infra.repositories.user import LocalCredentialRepository, UserRepository
from skillhub_api.logging import get_logger
from skillhub_api.services.auth.passwords import hash_password
from skillhub_api.settings import get_settings

logger = get_logger(__name__)


async def ensure_bootstrap_admin(session: AsyncSession) -> None:
    settings = get_settings()
    cfg = settings.bootstrap_admin
    if not cfg.enabled:
        return

    users = UserRepository(session)
    creds = LocalCredentialRepository(session)
    roles = RoleRepository(session)

    existing = await users.get(cfg.user_id)
    if existing is None:
        now = datetime.now(UTC)
        existing = UserAccount(
            id=cfg.user_id,
            display_name=cfg.display_name,
            email=cfg.email,
            status="ACTIVE",
            created_at=now,
            updated_at=now,
        )
        session.add(existing)
        await session.flush()
        logger.info("bootstrap.admin_user_created", user_id=cfg.user_id)

    if (await creds.find_by_user_id(cfg.user_id)) is None:
        session.add(
            LocalCredential(
                user_id=cfg.user_id,
                username=cfg.username,
                password_hash=hash_password(cfg.password.get_secret_value()),
                failed_attempts=0,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        )
        await session.flush()
        logger.info("bootstrap.admin_credential_created", user_id=cfg.user_id)

    super_admin = await roles.find_by_code(ROLE_SUPER_ADMIN)
    if super_admin is not None:
        await roles.bind_user(cfg.user_id, super_admin.id)
    await session.commit()
