"""Social rollup listeners.

Match the Java behavior: every star/unstar event triggers a full recount
on ``skill.star_count``; every rating event recomputes AVG + COUNT on
``skill.rating_avg`` / ``skill.rating_count``. Retries are idempotent
because the aggregation always reflects the current table state.

A direct UPDATE with a subquery keeps the rollup inside a single
statement, so the listener doesn't need to load the skill row first.
"""

from __future__ import annotations

from sqlalchemy import text

from skillhub_api.domain.events import (
    DomainEvent,
    SkillRatedEvent,
    SkillStarredEvent,
    SkillUnstarredEvent,
)
from skillhub_api.events.bus import EventBus
from skillhub_api.infra.db.session import AsyncSessionLocal
from skillhub_api.logging import get_logger

logger = get_logger(__name__)


async def _refresh_star_count(skill_id: int) -> None:
    async with AsyncSessionLocal()() as session:
        await session.execute(
            text(
                "UPDATE skill SET star_count = "
                "(SELECT COUNT(*) FROM skill_star WHERE skill_id = :id) "
                "WHERE id = :id"
            ),
            {"id": skill_id},
        )
        await session.commit()


async def _refresh_rating_stats(skill_id: int) -> None:
    async with AsyncSessionLocal()() as session:
        await session.execute(
            text(
                """
                UPDATE skill
                SET rating_count = COALESCE(r.cnt, 0),
                    rating_avg   = COALESCE(r.avg, 0)
                FROM (
                  SELECT COUNT(*) AS cnt, AVG(score)::numeric(3,2) AS avg
                  FROM skill_rating WHERE skill_id = :id
                ) AS r
                WHERE skill.id = :id
                """
            ),
            {"id": skill_id},
        )
        await session.commit()


async def _on_star_event(event: DomainEvent) -> None:
    assert isinstance(event, SkillStarredEvent | SkillUnstarredEvent)
    try:
        await _refresh_star_count(event.skill_id)
    except Exception as exc:  # pragma: no cover
        logger.error("social.star_rollup_failed", skill_id=event.skill_id, error=str(exc))


async def _on_rated(event: DomainEvent) -> None:
    assert isinstance(event, SkillRatedEvent)
    try:
        await _refresh_rating_stats(event.skill_id)
    except Exception as exc:  # pragma: no cover
        logger.error("social.rating_rollup_failed", skill_id=event.skill_id, error=str(exc))


def register_social_listeners(bus: EventBus) -> None:
    bus.subscribe(SkillStarredEvent, _on_star_event)
    bus.subscribe(SkillUnstarredEvent, _on_star_event)
    bus.subscribe(SkillRatedEvent, _on_rated)
