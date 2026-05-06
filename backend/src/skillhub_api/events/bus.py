"""Post-commit event bus.

Design: listeners are async callables registered at app startup. Services
buffer events via ``EventBus.enqueue(event)`` during a request; the router
calls ``await bus.dispatch()`` **after** the session commits. Listeners
then run concurrently via ``asyncio.TaskGroup``.

Rationale — from the plan §4 (Phase 4): the current Java listeners
(notification fan-out, search index update, star/rating rollup, label
search sync) are all short and latency-tolerant, so an in-process bus
avoids introducing a broker. For durability-critical listeners later, we
can opt them into ``dramatiq``/``arq`` without touching the producer side.

**Single-turn context only.** Each request gets its own buffered event
list via the ``EventBus.request_context()`` helper; there is no global
queue. This keeps the bus safe under concurrent requests without locks.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import TypeVar

from skillhub_api.domain.events import DomainEvent
from skillhub_api.logging import get_logger

logger = get_logger(__name__)

E = TypeVar("E", bound=DomainEvent)
Listener = Callable[[DomainEvent], Awaitable[None]]


_buffer: ContextVar[list[DomainEvent] | None] = ContextVar("skillhub_event_buffer", default=None)


@dataclass(slots=True)
class _Subscription:
    event_type: type[DomainEvent]
    handler: Listener


class EventBus:
    def __init__(self) -> None:
        self._subs: list[_Subscription] = []

    def subscribe(self, event_type: type[E], handler: Callable[[E], Awaitable[None]]) -> None:
        self._subs.append(_Subscription(event_type=event_type, handler=handler))  # type: ignore[arg-type]

    def enqueue(self, event: DomainEvent) -> None:
        """Add an event to the current request's buffer.

        Call sites must be inside a ``request_context()`` block (normally
        provided by the FastAPI middleware below). If the buffer is missing
        we treat that as a bug, not a silent drop — so we log and skip.
        """
        buf = _buffer.get()
        if buf is None:
            logger.warning(
                "events.enqueue_outside_request",
                event_type=event.__class__.__name__,
            )
            return
        buf.append(event)

    async def dispatch(self) -> None:
        """Fire all buffered events on listeners matching by type."""
        buf = _buffer.get() or []
        if not buf:
            return

        async def _run(sub: _Subscription, ev: DomainEvent) -> None:
            try:
                await sub.handler(ev)
            except Exception as exc:  # pragma: no cover — surfaced via logs
                logger.error(
                    "events.listener_failed",
                    event_type=ev.__class__.__name__,
                    handler=sub.handler.__qualname__,
                    error=str(exc),
                )

        try:
            async with asyncio.TaskGroup() as tg:
                for ev in buf:
                    for sub in self._subs:
                        if isinstance(ev, sub.event_type):
                            tg.create_task(_run(sub, ev))
        finally:
            buf.clear()

    @contextmanager
    def request_context(self):
        token = _buffer.set([])
        try:
            yield
        finally:
            _buffer.reset(token)


_singleton: EventBus | None = None


def get_event_bus() -> EventBus:
    global _singleton
    if _singleton is None:
        _singleton = EventBus()
    return _singleton


def reset_event_bus() -> None:
    """Used by tests to start with no subscriptions."""
    global _singleton
    _singleton = EventBus()
