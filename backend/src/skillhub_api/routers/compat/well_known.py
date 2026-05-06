"""Well-known metadata discovery — /.well-known/clawhub.json.

Legacy CLI tooling probes this URL at startup to learn where the API
lives. The only field required today is ``apiBase``; we preserve the
Java response shape verbatim.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["compat"])


@router.get("/.well-known/clawhub.json")
async def clawhub_well_known() -> dict[str, str]:
    return {"apiBase": "/api/v1"}
