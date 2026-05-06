"""Event-buffer middleware.

Wraps each request in ``bus.request_context()`` so services can safely
call ``bus.enqueue(event)``. After the response is produced, dispatch the
buffered events — this is the post-commit fan-out point.

If the response is a 4xx/5xx the events still fire: services are
responsible for rolling back via ``session.rollback()`` before returning
an error, in which case they should not have enqueued anything. This
mirrors Spring's ``@TransactionalEventListener(phase=AFTER_COMMIT)``.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from skillhub_api.events.bus import get_event_bus


class EventDispatchMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        bus = get_event_bus()
        with bus.request_context():
            response = await call_next(request)
            if 200 <= response.status_code < 400:
                await bus.dispatch()
        return response
