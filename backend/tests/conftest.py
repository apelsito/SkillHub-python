"""Shared test fixtures.

Integration fixtures (testcontainers-postgres / redis / minio) live alongside
the tests that need them so unit tests stay fast.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client() -> TestClient:
    from skillhub_api.main import create_app

    return TestClient(create_app())
