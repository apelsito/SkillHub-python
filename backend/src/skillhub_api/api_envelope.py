"""Java-compatible ``ApiResponse<T>`` envelope.

The Spring backend wraps every successful JSON body in
``{code, msg, data, timestamp, requestId}``. The existing React client
(``fetchJson`` in ``web/src/api/client.ts``) hard-codes this shape and
throws ``ApiError`` whenever ``code !== 0``. We match the shape so the
frontend works unchanged.

Error responses bypass this wrapper — they already return
``{code, message, details}`` via ``errors.py``, and the frontend's
``fetchJson`` only looks at ``code !== 0`` + HTTP status, which our
error bodies already violate in the expected way.

The Prometheus ``/metrics`` and the OpenAPI docs are exempted — they
return non-JSON bodies the scraper and Swagger UI expect verbatim.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

_EXEMPT_PATHS = (
    "/metrics",
    "/v3/api-docs",
    "/swagger-ui",
    "/redoc",
    "/openapi.json",
    "/.well-known/",
)


def _is_exempt(path: str) -> bool:
    return any(path.startswith(p) for p in _EXEMPT_PATHS)


class ApiEnvelopeMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        if _is_exempt(request.url.path):
            return response

        content_type = response.headers.get("content-type", "")
        if "application/json" not in content_type:
            return response

        # Only wrap 2xx bodies; 4xx/5xx already use our error shape which
        # the frontend parses through its ``code !== 0`` branch.
        if response.status_code < 200 or response.status_code >= 300:
            return response

        body = b""
        async for chunk in response.body_iterator:
            body += chunk

        if not body:
            data = None
        else:
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                return Response(
                    content=body,
                    status_code=response.status_code,
                    headers=dict(response.headers),
                )

        envelope = {
            "code": 0,
            "msg": "ok",
            "data": data,
            "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "requestId": request.headers.get("x-request-id") or uuid.uuid4().hex,
        }
        payload = json.dumps(envelope, default=str).encode("utf-8")

        # Reuse existing headers but fix Content-Length + Content-Type.
        headers = {k: v for k, v in response.headers.items() if k.lower() != "content-length"}
        headers["content-type"] = "application/json"
        return Response(
            content=payload, status_code=response.status_code, headers=headers
        )
