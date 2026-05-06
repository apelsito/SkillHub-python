from fastapi.testclient import TestClient


def test_healthz_returns_up(client: TestClient) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["data"] == {"status": "UP"}


def test_actuator_health_parity(client: TestClient) -> None:
    response = client.get("/actuator/health")
    assert response.status_code == 200
    assert response.json()["data"] == {"status": "UP"}


def test_api_v1_health(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["data"] == {"status": "UP"}


def test_openapi_document_served(client: TestClient) -> None:
    # /v3/api-docs is exempted from the envelope middleware so Swagger
    # tooling can parse the raw OpenAPI document directly.
    response = client.get("/v3/api-docs")
    assert response.status_code == 200
    body = response.json()
    assert body["info"]["title"] == "SkillHub API"
    assert "/healthz" in body["paths"]
    assert "/actuator/health" in body["paths"]
