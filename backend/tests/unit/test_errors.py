from fastapi import FastAPI
from fastapi.testclient import TestClient

from skillhub_api.errors import (
    ConflictError,
    DomainError,
    ForbiddenError,
    NotFoundError,
    UnauthorizedError,
    register_exception_handlers,
)


def _app_raising(exc: Exception) -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/boom")
    def boom() -> None:
        raise exc

    return app


def test_domain_error_shape() -> None:
    app = _app_raising(DomainError("X_BAD", "something bad", details={"field": "name"}))
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/boom")
    assert response.status_code == 400
    body = response.json()
    # ``code`` is the numeric HTTP status (Java envelope compat); the
    # symbolic code lives alongside as ``errorCode``.
    assert body["code"] == 400
    assert body["msg"] == "something bad"
    assert body["errorCode"] == "X_BAD"
    assert body["details"] == {"field": "name"}


def test_not_found_error_maps_to_404() -> None:
    app = _app_raising(NotFoundError("SKILL_NOT_FOUND", "skill missing"))
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/boom")
    assert response.status_code == 404
    body = response.json()
    assert body["code"] == 404
    assert body["errorCode"] == "SKILL_NOT_FOUND"


def test_conflict_error_maps_to_409() -> None:
    app = _app_raising(ConflictError("SLUG_TAKEN", "slug already exists"))
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/boom")
    assert response.status_code == 409


def test_forbidden_error_maps_to_403() -> None:
    app = _app_raising(ForbiddenError("NOT_ALLOWED", "no permission"))
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/boom")
    assert response.status_code == 403


def test_unauthorized_error_maps_to_401() -> None:
    app = _app_raising(UnauthorizedError("UNAUTHENTICATED", "login required"))
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/boom")
    assert response.status_code == 401
    assert response.json()["errorCode"] == "UNAUTHENTICATED"
