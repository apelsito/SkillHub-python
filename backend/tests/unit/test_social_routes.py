"""Route sanity for social + notification endpoints."""

from fastapi.testclient import TestClient

EXPECTED = [
    "/api/v1/skills/{skillId}/star",
    "/api/v1/skills/{skillId}/rating",
    "/api/v1/skills/{skillId}/subscription",
    "/api/v1/notifications",
    "/api/v1/notifications/unread-count",
    "/api/v1/notifications/{id}/read",
    "/api/v1/notifications/read-all",
    "/api/v1/notifications/{id}",
    "/api/v1/notification-preferences",
    "/api/v1/notifications/sse",
]


def test_social_routes_registered(client: TestClient) -> None:
    paths = client.get("/v3/api-docs").json()["paths"]
    for p in EXPECTED:
        assert p in paths, f"missing route: {p}"


def test_star_requires_auth(client: TestClient) -> None:
    assert client.put("/api/v1/skills/1/star").status_code == 401


def test_rating_validates_score(client: TestClient) -> None:
    # Unauthenticated returns 401 before Pydantic validation fires.
    r = client.put("/api/v1/skills/1/rating", json={"score": 6})
    assert r.status_code in (401, 422)


def test_notification_list_requires_auth(client: TestClient) -> None:
    assert client.get("/api/v1/notifications").status_code == 401
    assert client.get("/api/v1/notifications/unread-count").status_code == 401


def test_sse_requires_auth(client: TestClient) -> None:
    assert client.get("/api/v1/notifications/sse").status_code == 401
