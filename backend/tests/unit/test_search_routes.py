from fastapi.testclient import TestClient


def test_search_route_registered(client: TestClient) -> None:
    paths = client.get("/v3/api-docs").json()["paths"]
    assert "/api/v1/skills/search" in paths


def test_search_rejects_invalid_sort(client: TestClient) -> None:
    r = client.get("/api/v1/skills/search", params={"sort": "bogus"})
    # Pydantic validation fires before the DB dep.
    assert r.status_code == 422
