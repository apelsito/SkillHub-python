"""OpenAPI sanity — all Phase 4 routes exposed."""

from fastapi.testclient import TestClient

EXPECTED = [
    "/api/v1/reviews",
    "/api/v1/reviews/pending",
    "/api/v1/reviews/mine",
    "/api/v1/reviews/{id}/approve",
    "/api/v1/reviews/{id}/reject",
    "/api/v1/skills/{skillId}/reports",
    "/api/v1/admin/skill-reports",
    "/api/v1/admin/skill-reports/{id}/handle",
    "/api/v1/admin/audit-logs",
    "/api/v1/admin/promotions",
    "/api/v1/admin/promotions/{promotion_id}/approve",
    "/api/v1/admin/promotions/{promotion_id}/reject",
    "/api/v1/me/profile-change",
    "/api/v1/admin/profile-changes/{id}/approve",
    "/api/v1/admin/profile-changes/{id}/reject",
]


def test_governance_routes_registered(client: TestClient) -> None:
    paths = client.get("/v3/api-docs").json()["paths"]
    for p in EXPECTED:
        assert p in paths, f"missing route: {p}"


def test_audit_requires_permission(client: TestClient) -> None:
    r = client.get("/api/v1/admin/audit-logs")
    # Unauthenticated → 401; authenticated-but-unauthorized covered in integration.
    assert r.status_code == 401


def test_report_submit_requires_auth(client: TestClient) -> None:
    r = client.post("/api/v1/skills/1/reports", json={"reason": "spam"})
    assert r.status_code == 401
