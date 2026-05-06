"""Global error types + FastAPI exception handlers.

The JSON error shape mirrors Spring's ``@ControllerAdvice`` output so the React
frontend's error-handling paths keep working without modification.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class DomainError(Exception):
    """Raised by domain services. Carries an HTTP status + error code."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}


class NotFoundError(DomainError):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(code, message, status.HTTP_404_NOT_FOUND, details)


class ConflictError(DomainError):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(code, message, status.HTTP_409_CONFLICT, details)


class ForbiddenError(DomainError):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(code, message, status.HTTP_403_FORBIDDEN, details)


class UnauthorizedError(DomainError):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(code, message, status.HTTP_401_UNAUTHORIZED, details)


def _error_body(
    code: str, message: str, *, status_code: int, details: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Shape compatible with the React client's ``ApiEnvelope`` reader.

    The client throws on ``code !== 0`` and reads ``msg`` for the message.
    We pass the HTTP status as the numeric ``code`` (always non-zero) and
    keep the original symbolic ``errorCode`` alongside so server logs +
    admin tooling can still key on it.
    """
    body: dict[str, Any] = {
        "code": status_code,
        "msg": message,
        "errorCode": code,
        "data": None,
    }
    if details:
        body["details"] = details
    return body


async def _handle_domain_error(_request: Request, exc: DomainError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_body(
            exc.code, exc.message, status_code=exc.status_code, details=exc.details
        ),
    )


async def _handle_http_exception(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = {
        status.HTTP_400_BAD_REQUEST: "BAD_REQUEST",
        status.HTTP_401_UNAUTHORIZED: "UNAUTHORIZED",
        status.HTTP_403_FORBIDDEN: "FORBIDDEN",
        status.HTTP_404_NOT_FOUND: "NOT_FOUND",
        status.HTTP_405_METHOD_NOT_ALLOWED: "METHOD_NOT_ALLOWED",
        status.HTTP_409_CONFLICT: "CONFLICT",
        status.HTTP_422_UNPROCESSABLE_ENTITY: "UNPROCESSABLE_ENTITY",
        status.HTTP_429_TOO_MANY_REQUESTS: "TOO_MANY_REQUESTS",
    }.get(exc.status_code, "HTTP_ERROR")
    message = str(exc.detail) if exc.detail is not None else ""
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_body(code, message, status_code=exc.status_code),
    )


async def _handle_validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=_error_body(
            "VALIDATION_ERROR",
            "request validation failed",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details={"errors": exc.errors()},
        ),
    )


async def _handle_unexpected(_request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=_error_body(
            "INTERNAL_ERROR",
            "internal server error",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        ),
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(DomainError, _handle_domain_error)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, _handle_http_exception)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, _handle_validation_error)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, _handle_unexpected)
