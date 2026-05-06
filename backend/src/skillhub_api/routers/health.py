"""Health endpoints.

We expose both `/healthz` (modern convention) and `/actuator/health` (Spring
Boot compatibility) so existing infra probes and dashboards keep working
without changes.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["health"])


class Health(BaseModel):
    status: str


@router.get("/healthz", response_model=Health)
async def healthz() -> Health:
    return Health(status="UP")


@router.get("/actuator/health", response_model=Health)
async def actuator_health() -> Health:
    return Health(status="UP")


@router.get("/api/v1/health", response_model=Health)
async def api_v1_health() -> Health:
    return Health(status="UP")
