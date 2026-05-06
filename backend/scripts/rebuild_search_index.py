"""CLI: rebuild ``skill_search_document`` from scratch.

Usage:
  uv run python scripts/rebuild_search_index.py
"""

from __future__ import annotations

import asyncio
import sys


async def _main() -> int:
    from skillhub_api.infra.db.session import AsyncSessionLocal, dispose_engine
    from skillhub_api.search.rebuild import rebuild_all

    async with AsyncSessionLocal()() as session:
        count = await rebuild_all(session)
    await dispose_engine()
    print(f"rebuilt {count} skill(s)")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
