"""Unit tests for Phase 8 infra: scheduler, stream consumer, log sanitizer."""

from __future__ import annotations

from skillhub_api.logging_sanitizer import sanitize_log_record
from skillhub_api.scheduling import SchedulerManager


def test_sanitize_redacts_sensitive_fields() -> None:
    event = {
        "event": "login",
        "password": "hunter2",
        "api_key": "abcdef",
        "authorization": "Bearer xyz",
        "nested": {"Token": "secret", "user": "alice"},
        "items": [{"secret_value": "shh", "name": "ok"}],
    }
    cleaned = sanitize_log_record(None, "info", event)
    assert cleaned["password"] == "***"
    assert cleaned["api_key"] == "***"
    assert cleaned["authorization"] == "***"
    assert cleaned["nested"]["Token"] == "***"
    assert cleaned["nested"]["user"] == "alice"
    assert cleaned["items"][0]["secret_value"] == "***"
    assert cleaned["items"][0]["name"] == "ok"
    assert cleaned["event"] == "login"


async def test_scheduler_start_shutdown_is_idempotent() -> None:
    mgr = SchedulerManager()
    mgr.start()
    try:
        assert mgr.jobs(), "scheduler should register maintenance jobs"
        # Starting again is a no-op.
        mgr.start()
    finally:
        await mgr.shutdown()


async def test_scheduler_shutdown_is_safe_when_not_started() -> None:
    mgr = SchedulerManager()
    await mgr.shutdown()
    assert mgr.jobs() == []


async def test_scheduler_registers_expected_jobs() -> None:
    mgr = SchedulerManager()
    mgr.start()
    try:
        ids = {j["id"] for j in mgr.jobs()}
        assert ids == {
            "idempotency_cleanup",
            "idempotency_stale",
            "storage_compensation",
            "notification_cleanup",
        }
    finally:
        await mgr.shutdown()
