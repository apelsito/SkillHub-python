"""Retired web-contract shim.

All frontend-declared /api/web routes are now served by real routers or aliases.
The module stays importable so older app wiring remains stable.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["web-contract"])
