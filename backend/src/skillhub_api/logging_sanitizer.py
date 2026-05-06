"""Scrub sensitive fields from structured log events.

Mirrors the Java ``SensitiveLogSanitizer`` contract: any key whose name
looks like a secret is replaced with ``***`` before the JSON renderer
serializes the record. structlog makes this a one-liner — we attach it
as the last processor before the renderer.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

_SENSITIVE_RE = re.compile(
    r"(password|passwd|secret|token|api[_-]?key|authorization|cookie|session[_-]?id)",
    re.IGNORECASE,
)


def _scrub(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {k: ("***" if _SENSITIVE_RE.search(k) else _scrub(v)) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return type(value)(_scrub(v) for v in value)
    return value


def sanitize_log_record(_logger, _method_name: str, event_dict: dict) -> dict:
    return _scrub(event_dict)
