"""Skill report workflow."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from skillhub_api.domain.events import ReportResolvedEvent, ReportSubmittedEvent
from skillhub_api.errors import ConflictError, NotFoundError
from skillhub_api.events.bus import EventBus
from skillhub_api.infra.db.models.governance import SkillReport
from skillhub_api.infra.repositories.governance import SkillReportRepository
from skillhub_api.infra.repositories.skill import SkillRepository

VALID_HANDLE_ACTIONS = {"DISMISSED", "HIDDEN", "REMOVED"}


class SkillReportService:
    def __init__(self, session: AsyncSession, bus: EventBus) -> None:
        self._session = session
        self._bus = bus
        self._reports = SkillReportRepository(session)
        self._skills = SkillRepository(session)

    async def submit(
        self,
        *,
        skill_id: int,
        reporter_id: str,
        reason: str,
        details: str | None,
    ) -> SkillReport:
        skill = await self._skills.get(skill_id)
        if skill is None:
            raise NotFoundError("SKILL_NOT_FOUND", "skill not found")

        row = await self._reports.create(
            skill_id=skill.id,
            namespace_id=skill.namespace_id,
            reporter_id=reporter_id,
            reason=reason,
            details=details,
        )
        self._bus.enqueue(
            ReportSubmittedEvent(
                occurred_at=datetime.now(UTC),
                skill_id=skill.id,
                report_id=row.id,
                reporter_id=reporter_id,
            )
        )
        return row

    async def handle(
        self,
        *,
        report_id: int,
        handler_id: str,
        action: str,
        comment: str | None,
    ) -> SkillReport:
        if action not in VALID_HANDLE_ACTIONS:
            raise ConflictError("INVALID_ACTION", f"action must be one of {VALID_HANDLE_ACTIONS}")
        row = await self._reports.get(report_id)
        if row is None:
            raise NotFoundError("REPORT_NOT_FOUND", "report not found")
        if row.status != "PENDING":
            raise ConflictError("REPORT_NOT_PENDING", f"report already {row.status}")

        now = datetime.now(UTC)
        row.status = action
        row.handled_by = handler_id
        row.handle_comment = comment
        row.handled_at = now

        # Apply side-effects: HIDDEN flags the skill hidden, REMOVED archives.
        if action in {"HIDDEN", "REMOVED"}:
            skill = await self._skills.get(row.skill_id)
            if skill is not None:
                skill.hidden = True
                skill.hidden_at = now
                skill.hidden_by = handler_id
                if action == "REMOVED":
                    skill.status = "ARCHIVED"

        self._bus.enqueue(
            ReportResolvedEvent(
                occurred_at=now,
                skill_id=row.skill_id,
                report_id=row.id,
                reporter_id=row.reporter_id,
                handler_id=handler_id,
                action=action,
            )
        )
        return row

    async def list_pending(self, *, limit: int, offset: int):
        return await self._reports.list_pending(limit=limit, offset=offset)
