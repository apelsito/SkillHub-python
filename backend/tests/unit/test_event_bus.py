from datetime import UTC, datetime

import pytest

from skillhub_api.domain.events import SkillPublishedEvent, SkillStarredEvent
from skillhub_api.events.bus import EventBus


async def test_enqueue_dispatches_to_typed_listener() -> None:
    bus = EventBus()
    collected: list = []

    async def listener(event: SkillPublishedEvent) -> None:
        collected.append(event)

    bus.subscribe(SkillPublishedEvent, listener)
    with bus.request_context():
        bus.enqueue(
            SkillPublishedEvent(
                occurred_at=datetime.now(UTC),
                skill_id=1,
                version_id=2,
                publisher_id="u",
            )
        )
        await bus.dispatch()
    assert len(collected) == 1
    assert collected[0].skill_id == 1


async def test_dispatch_filters_by_type() -> None:
    bus = EventBus()
    published: list = []
    starred: list = []

    async def on_pub(e: SkillPublishedEvent) -> None:
        published.append(e)

    async def on_star(e: SkillStarredEvent) -> None:
        starred.append(e)

    bus.subscribe(SkillPublishedEvent, on_pub)
    bus.subscribe(SkillStarredEvent, on_star)

    with bus.request_context():
        bus.enqueue(SkillStarredEvent(occurred_at=datetime.now(UTC), skill_id=1, user_id="u"))
        await bus.dispatch()

    assert len(published) == 0
    assert len(starred) == 1


async def test_enqueue_outside_context_does_not_raise() -> None:
    bus = EventBus()
    bus.enqueue(SkillStarredEvent(occurred_at=datetime.now(UTC), skill_id=1, user_id="u"))


async def test_failing_listener_does_not_block_others() -> None:
    bus = EventBus()
    other_called = False

    async def boom(e) -> None:
        raise RuntimeError("nope")

    async def other(e) -> None:
        nonlocal other_called
        other_called = True

    bus.subscribe(SkillStarredEvent, boom)
    bus.subscribe(SkillStarredEvent, other)

    with bus.request_context():
        bus.enqueue(SkillStarredEvent(occurred_at=datetime.now(UTC), skill_id=1, user_id="u"))
        await bus.dispatch()

    assert other_called


@pytest.mark.parametrize("n", [0, 1, 5])
async def test_buffer_clears_after_dispatch(n: int) -> None:
    bus = EventBus()
    calls: list = []

    async def listener(e) -> None:
        calls.append(e)

    bus.subscribe(SkillStarredEvent, listener)
    with bus.request_context():
        for i in range(n):
            bus.enqueue(SkillStarredEvent(occurred_at=datetime.now(UTC), skill_id=i, user_id="u"))
        await bus.dispatch()
        # Second dispatch is a no-op (buffer cleared).
        await bus.dispatch()
    assert len(calls) == n
