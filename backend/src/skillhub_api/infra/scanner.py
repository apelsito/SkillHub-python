"""HTTP client for the external skill-scanner microservice.

Ports ``SkillScannerService.java`` to ``httpx.AsyncClient``. Two modes
are supported — just like the Java service:

  * ``local``  — scanner has filesystem access to the already-extracted
    skill directory. POST JSON to ``/scan``.
  * ``upload`` — scanner runs out-of-process / remote. POST a multipart
    upload to ``/scan-upload``.

Retries: bounded, exponential back-off with jitter handled by
``httpx``'s transport — tuned by ``SKILLHUB_SECURITY_SCANNER_RETRY_MAX``.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

import httpx

from skillhub_api.logging import get_logger
from skillhub_api.settings import ScannerSettings, get_settings

logger = get_logger(__name__)


@dataclass(slots=True)
class ScannerFinding:
    id: str
    rule_id: str
    severity: str
    category: str | None
    title: str
    description: str | None
    file_path: str | None
    line_number: int | None
    snippet: str | None
    remediation: str | None
    analyzer: str | None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ScannerResult:
    scan_id: str
    skill_name: str | None
    is_safe: bool
    max_severity: str | None
    findings_count: int
    findings: list[ScannerFinding]
    scan_duration_seconds: float | None
    timestamp: str | None


def _parse_finding(payload: dict[str, Any]) -> ScannerFinding:
    return ScannerFinding(
        id=str(payload.get("id", "")),
        rule_id=str(payload.get("rule_id", "")),
        severity=str(payload.get("severity", "INFO")),
        category=payload.get("category"),
        title=str(payload.get("title", "")),
        description=payload.get("description"),
        file_path=payload.get("file_path"),
        line_number=payload.get("line_number"),
        snippet=payload.get("snippet"),
        remediation=payload.get("remediation"),
        analyzer=payload.get("analyzer"),
        metadata=payload.get("metadata") or {},
    )


def _parse_result(payload: dict[str, Any]) -> ScannerResult:
    return ScannerResult(
        scan_id=str(payload.get("scan_id", "")),
        skill_name=payload.get("skill_name"),
        is_safe=bool(payload.get("is_safe", False)),
        max_severity=payload.get("max_severity"),
        findings_count=int(payload.get("findings_count", 0)),
        findings=[_parse_finding(f) for f in payload.get("findings", [])],
        scan_duration_seconds=payload.get("scan_duration_seconds"),
        timestamp=payload.get("timestamp"),
    )


class SkillScannerClient:
    def __init__(self, settings: ScannerSettings | None = None) -> None:
        self._settings = settings or get_settings().scanner

    def _timeout(self) -> httpx.Timeout:
        s = self._settings
        return httpx.Timeout(
            connect=s.connect_timeout_ms / 1000.0,
            read=s.read_timeout_ms / 1000.0,
            write=s.read_timeout_ms / 1000.0,
            pool=s.connect_timeout_ms / 1000.0,
        )

    async def is_healthy(self) -> bool:
        if not self._settings.enabled:
            return False
        try:
            async with httpx.AsyncClient(
                base_url=self._settings.base_url, timeout=self._timeout()
            ) as c:
                response = await c.get("/health")
                return 200 <= response.status_code < 300
        except httpx.HTTPError:
            return False

    async def scan_directory(self, skill_directory: str) -> ScannerResult:
        if not self._settings.enabled:
            raise RuntimeError("scanner is disabled")
        body: dict[str, Any] = {
            "skill_directory": skill_directory,
            "use_behavioral": True,
            "use_llm": False,
            "enable_meta": False,
            "use_aidefense": False,
            "use_virustotal": False,
            "use_trigger": False,
        }
        return await self._post_with_retry(path="/scan", json=body)

    async def scan_upload(
        self, *, filename: str, contents: bytes, content_type: str = "application/zip"
    ) -> ScannerResult:
        if not self._settings.enabled:
            raise RuntimeError("scanner is disabled")
        files = {"file": (filename, contents, content_type)}
        return await self._post_with_retry(path="/scan-upload", files=files)

    async def _post_with_retry(
        self,
        *,
        path: str,
        json: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
    ) -> ScannerResult:
        last_exc: Exception | None = None
        for attempt in range(1, max(1, self._settings.retry_max_attempts) + 1):
            try:
                async with httpx.AsyncClient(
                    base_url=self._settings.base_url, timeout=self._timeout()
                ) as c:
                    response = await c.post(path, json=json, files=files)
                response.raise_for_status()
                return _parse_result(response.json())
            except httpx.HTTPError as exc:
                last_exc = exc
                logger.warning(
                    "scanner.retry",
                    path=path,
                    attempt=attempt,
                    max_attempts=self._settings.retry_max_attempts,
                    error=str(exc),
                )
                await asyncio.sleep(min(2.0, 0.25 * (2 ** (attempt - 1))))
        assert last_exc is not None
        raise last_exc
