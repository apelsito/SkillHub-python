"""ORM models for every table in the V40-equivalent schema.

Importing this package side-effects-registers every table on ``Base.metadata``.
Alembic's env.py imports it so ``target_metadata`` reflects the full schema.
"""

from skillhub_api.infra.db.models import (  # noqa: F401
    audit,
    auth,
    governance,
    idempotency,
    label,
    namespace,
    notification,
    search,
    security,
    skill,
    social,
    storage_compensation,
    user,
)
