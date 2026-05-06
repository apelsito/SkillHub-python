"""Unit tests for the in-memory SSE stream manager."""

from __future__ import annotations

import asyncio

import pytest

from skillhub_api.sse.manager import MAX_PER_USER, NotificationStreamManager


async def test_publish_delivers_to_connected_user() -> None:
    mgr = NotificationStreamManager()
    conn = await mgr.connect("alice")
    await mgr.publish(recipient_id="alice", payload={"hello": "world"})

    msg = await asyncio.wait_for(conn.queue.get(), timeout=1.0)
    assert '"hello"' in msg and '"world"' in msg
    await mgr.disconnect(conn)


async def test_publish_ignores_unknown_recipient() -> None:
    mgr = NotificationStreamManager()
    conn = await mgr.connect("alice")
    await mgr.publish(recipient_id="bob", payload={"x": 1})
    assert conn.queue.empty()
    await mgr.disconnect(conn)


async def test_per_user_connection_limit_evicts_oldest() -> None:
    mgr = NotificationStreamManager()
    conns = [await mgr.connect("alice") for _ in range(MAX_PER_USER)]
    assert len(mgr._by_user["alice"]) == MAX_PER_USER

    # Next connect evicts the oldest — its queue receives the sentinel.
    await mgr.connect("alice")
    evicted = conns[0]
    msg = await asyncio.wait_for(evicted.queue.get(), timeout=1.0)
    assert msg == "__closed__"


@pytest.mark.parametrize("n", [1, 3, 10])
async def test_concurrent_publishes_do_not_drop_on_small_volume(n: int) -> None:
    mgr = NotificationStreamManager()
    conn = await mgr.connect("alice")
    for i in range(n):
        await mgr.publish(recipient_id="alice", payload={"i": i})
    received: list[str] = []
    for _ in range(n):
        received.append(await asyncio.wait_for(conn.queue.get(), timeout=1.0))
    assert len(received) == n
    await mgr.disconnect(conn)


async def test_disconnect_clears_empty_user_slot() -> None:
    mgr = NotificationStreamManager()
    conn = await mgr.connect("alice")
    await mgr.disconnect(conn)
    assert "alice" not in mgr._by_user
