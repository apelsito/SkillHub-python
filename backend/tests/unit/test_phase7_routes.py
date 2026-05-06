"""Route-sanity smoke for Phase 7: admin, labels, tags, scanner, compat."""

from fastapi.testclient import TestClient

EXPECTED = [
    # admin/skills
    "/api/v1/admin/skills/{skillId}/hide",
    "/api/v1/admin/skills/{skillId}/unhide",
    "/api/v1/admin/skills/versions/{versionId}/yank",
    # admin/users
    "/api/v1/admin/users",
    "/api/v1/admin/users/{userId}/role",
    "/api/v1/admin/users/{userId}/status",
    "/api/v1/admin/users/{userId}/approve",
    "/api/v1/admin/users/{userId}/disable",
    "/api/v1/admin/users/{userId}/enable",
    "/api/v1/admin/users/{userId}/password-reset",
    # admin/profile-reviews
    "/api/v1/admin/profile-reviews",
    # admin/labels
    "/api/v1/admin/labels",
    "/api/v1/admin/labels/{slug}",
    "/api/v1/admin/labels/sort-order",
    # admin/search
    "/api/v1/admin/search/rebuild",
    # public labels + skill labels/tags
    "/api/v1/labels",
    "/api/v1/skills/{namespace}/{slug}/labels",
    "/api/v1/skills/{namespace}/{slug}/labels/{labelSlug}",
    "/api/v1/skills/{namespace}/{slug}/tags",
    "/api/v1/skills/{namespace}/{slug}/tags/{tagName}",
    # compat
    "/api/v1/search",
    "/api/v1/skills",
    "/api/v1/skills/{canonicalSlug}",
    "/api/v1/download/{canonicalSlug}",
    "/api/v1/whoami",
    "/api/v1/resolve",
]


def test_phase7_routes_registered(client: TestClient) -> None:
    paths = client.get("/v3/api-docs").json()["paths"]
    for p in EXPECTED:
        assert p in paths, f"missing route: {p}"


def test_well_known_returns_api_base(client: TestClient) -> None:
    r = client.get("/.well-known/clawhub.json")
    assert r.status_code == 200
    assert r.json() == {"apiBase": "/api/v1"}


def test_admin_endpoints_require_auth(client: TestClient) -> None:
    for path in (
        "/api/v1/admin/users",
        "/api/v1/admin/labels",
        "/api/v1/admin/profile-reviews",
    ):
        assert client.get(path).status_code == 401, path


def test_admin_skill_hide_rejects_unauth(client: TestClient) -> None:
    r = client.post("/api/v1/admin/skills/1/hide", json={"reason": "test"})
    assert r.status_code == 401


def test_whoami_unauthenticated_returns_flag(client: TestClient) -> None:
    r = client.get("/api/v1/whoami")
    assert r.status_code == 200
    # /api/v1/* is wrapped by the envelope middleware; payload lives in `data`.
    assert r.json()["data"] == {"authenticated": False}


def test_compat_resolve_requires_slug(client: TestClient) -> None:
    r = client.get("/api/v1/resolve")
    assert r.status_code == 422


def test_compat_publish_requires_auth(client: TestClient) -> None:
    r = client.post("/api/v1/publish")
    assert r.status_code == 401


def test_tag_request_validates_target_version() -> None:
    import pytest
    from pydantic import ValidationError

    from skillhub_api.schemas.admin import TagRequest

    with pytest.raises(ValidationError):
        TagRequest(target_version="")
