"""Sanity checks that Phase 2 routes are registered in the OpenAPI doc."""

from pathlib import Path
import re

from fastapi.testclient import TestClient


def test_auth_routes_are_exposed(client: TestClient) -> None:
    body = client.get("/v3/api-docs").json()
    paths = body["paths"]
    for p in [
        "/api/v1/auth/local/register",
        "/api/v1/auth/local/login",
        "/api/v1/auth/local/logout",
        "/api/v1/auth/logout",
        "/api/v1/auth/local/change-password",
        "/api/v1/auth/local/password-reset/request",
        "/api/v1/auth/local/password-reset/confirm",
        "/api/v1/auth/me",
        "/api/v1/tokens",
        "/api/v1/tokens/{id}",
        "/api/v1/auth/direct/login",
        "/api/v1/auth/session/bootstrap",
        "/login/oauth2/authorization/{provider}",
        "/login/oauth2/code/{provider}",
    ]:
        assert p in paths, f"missing route: {p}"


def test_frontend_web_contract_paths_are_exposed(client: TestClient) -> None:
    body = client.get("/v3/api-docs").json()
    backend_paths = set(body["paths"])
    schema_path = (
        Path(__file__).resolve().parents[3]
        / "frontend"
        / "src"
        / "api"
        / "generated"
        / "schema.d.ts"
    )
    frontend_paths = set(re.findall(r'"(/api/web/[^"]+)"', schema_path.read_text()))
    missing = sorted(frontend_paths - backend_paths)
    assert missing == []


def test_core_web_routes_are_exposed(client: TestClient) -> None:
    body = client.get("/v3/api-docs").json()
    paths = body["paths"]
    assert "/api/web/skills" in paths
    assert "/api/web/labels" in paths
    assert "/api/web/skills/{namespace}/{slug}" in paths


def test_me_requires_auth(client: TestClient) -> None:
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401
    body = response.json()
    assert body["errorCode"] == "UNAUTHENTICATED"


def test_tokens_list_requires_auth(client: TestClient) -> None:
    assert client.get("/api/v1/tokens").status_code == 401


def test_oauth_authorize_reports_unconfigured_provider(client: TestClient) -> None:
    r = client.get("/login/oauth2/authorization/github", follow_redirects=False)
    assert r.status_code == 404
    assert r.json()["errorCode"] == "NOT_FOUND"
    r = client.get("/login/oauth2/authorization/unknown", follow_redirects=False)
    assert r.status_code == 404
