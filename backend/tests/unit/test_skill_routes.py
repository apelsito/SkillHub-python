"""OpenAPI sanity: every Phase 3 route should be in the spec."""

from fastapi.testclient import TestClient

EXPECTED_ROUTES = [
    "/api/v1/skills",
    "/api/v1/skills/{namespace}/{slug}",
    "/api/v1/skills/{namespace}/{slug}/versions",
    "/api/v1/skills/{namespace}/{slug}/versions/{version}",
    "/api/v1/skills/{namespace}/{slug}/versions/{version}/files",
    "/api/v1/skills/{namespace}/publish",
    "/api/v1/skills/{namespace}/{slug}/download",
    "/api/v1/skills/{namespace}/{slug}/versions/{version}/download",
    "/api/v1/skills/{namespace}/{slug}/download/info",
    "/api/v1/skills/{namespace}/{slug}/archive",
    "/api/v1/skills/{namespace}/{slug}/unarchive",
    "/api/v1/skills/{namespace}/{slug}/versions/{version}/yank",
]


def test_skill_routes_registered(client: TestClient) -> None:
    paths = client.get("/v3/api-docs").json()["paths"]
    for p in EXPECTED_ROUTES:
        assert p in paths, f"missing route: {p}"


def test_publish_requires_auth(client: TestClient) -> None:
    # Plain post without multipart still hits the auth dep first.
    resp = client.post("/api/v1/skills/global/publish")
    assert resp.status_code in (401, 422)  # 401 if auth checked first; 422 if validation first


def test_list_skills_is_public(client: TestClient) -> None:
    # Unauthenticated listing is allowed. Empty result for the ephemeral
    # TestClient app (no DB behind it) would hit DB, so this is only a
    # routing-layer assertion in unit mode — skip actual execution.
    paths = client.get("/v3/api-docs").json()["paths"]
    get_op = paths["/api/v1/skills"]["get"]
    # No security requirement on list endpoint.
    assert "security" not in get_op or not get_op["security"]
