"""Unit tests for the scanner HTTP client using respx to mock httpx."""

from __future__ import annotations

import httpx
import pytest
import respx

from skillhub_api.infra.scanner import SkillScannerClient
from skillhub_api.settings import ScannerSettings


@pytest.fixture
def enabled_settings() -> ScannerSettings:
    cfg = ScannerSettings()
    cfg.enabled = True
    cfg.base_url = "http://scanner.test"
    cfg.retry_max_attempts = 2
    return cfg


async def test_health_returns_true_on_2xx(enabled_settings: ScannerSettings) -> None:
    client = SkillScannerClient(enabled_settings)
    with respx.mock(base_url="http://scanner.test", assert_all_mocked=True) as router:
        router.get("/health").mock(return_value=httpx.Response(200, json={"ok": True}))
        assert await client.is_healthy() is True


async def test_health_returns_false_when_disabled() -> None:
    cfg = ScannerSettings()
    cfg.enabled = False
    assert await SkillScannerClient(cfg).is_healthy() is False


async def test_scan_upload_retries_on_transient_error(
    enabled_settings: ScannerSettings,
) -> None:
    client = SkillScannerClient(enabled_settings)
    with respx.mock(base_url="http://scanner.test", assert_all_mocked=True) as router:
        route = router.post("/scan-upload").mock(
            side_effect=[
                httpx.Response(503, json={"error": "busy"}),
                httpx.Response(
                    200,
                    json={
                        "scan_id": "abc",
                        "is_safe": True,
                        "max_severity": None,
                        "findings_count": 0,
                        "findings": [],
                    },
                ),
            ]
        )
        result = await client.scan_upload(filename="x.zip", contents=b"zip")
        assert result.scan_id == "abc"
        assert route.call_count == 2


async def test_scan_directory_parses_findings(
    enabled_settings: ScannerSettings,
) -> None:
    client = SkillScannerClient(enabled_settings)
    with respx.mock(base_url="http://scanner.test", assert_all_mocked=True) as router:
        router.post("/scan").mock(
            return_value=httpx.Response(
                200,
                json={
                    "scan_id": "s1",
                    "is_safe": False,
                    "max_severity": "HIGH",
                    "findings_count": 1,
                    "findings": [
                        {
                            "id": "f1",
                            "rule_id": "R001",
                            "severity": "HIGH",
                            "category": "code",
                            "title": "shell exec",
                            "description": "uses os.system",
                            "file_path": "src/main.py",
                            "line_number": 12,
                            "metadata": {"score": 0.9},
                        }
                    ],
                },
            )
        )
        result = await client.scan_directory("/tmp/skill")
        assert result.is_safe is False
        assert result.findings[0].rule_id == "R001"
        assert result.findings[0].metadata == {"score": 0.9}
