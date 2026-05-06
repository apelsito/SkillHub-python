"""Governance repositories: review_task, promotion_request, skill_report."""

from __future__ import annotations

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from skillhub_api.infra.db.models.governance import (
    PromotionRequest,
    ReviewTask,
    SkillReport,
)


class ReviewTaskRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_pending_for_version(self, skill_version_id: int) -> ReviewTask | None:
        stmt = (
            select(ReviewTask)
            .where(
                and_(
                    ReviewTask.skill_version_id == skill_version_id,
                    ReviewTask.status == "PENDING",
                )
            )
            .limit(1)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def create(
        self,
        *,
        skill_version_id: int,
        namespace_id: int,
        submitted_by: str,
    ) -> ReviewTask:
        row = ReviewTask(
            skill_version_id=skill_version_id,
            namespace_id=namespace_id,
            status="PENDING",
            version=1,
            submitted_by=submitted_by,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def get(self, review_id: int) -> ReviewTask | None:
        return await self._session.get(ReviewTask, review_id)

    async def list_pending(
        self, *, namespace_id: int | None, limit: int, offset: int
    ) -> tuple[list[ReviewTask], int]:
        base = select(ReviewTask).where(ReviewTask.status == "PENDING")
        if namespace_id is not None:
            base = base.where(ReviewTask.namespace_id == namespace_id)
        total = (
            await self._session.execute(select(func.count()).select_from(base.subquery()))
        ).scalar_one()
        stmt = base.order_by(ReviewTask.submitted_at.asc()).offset(offset).limit(limit)
        rows = list((await self._session.execute(stmt)).scalars())
        return rows, total

    async def list_for_submitter(
        self, submitter_id: str, *, limit: int, offset: int
    ) -> tuple[list[ReviewTask], int]:
        base = select(ReviewTask).where(ReviewTask.submitted_by == submitter_id)
        total = (
            await self._session.execute(select(func.count()).select_from(base.subquery()))
        ).scalar_one()
        stmt = base.order_by(ReviewTask.submitted_at.desc()).offset(offset).limit(limit)
        rows = list((await self._session.execute(stmt)).scalars())
        return rows, total


class SkillReportRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        skill_id: int,
        namespace_id: int,
        reporter_id: str,
        reason: str,
        details: str | None,
    ) -> SkillReport:
        row = SkillReport(
            skill_id=skill_id,
            namespace_id=namespace_id,
            reporter_id=reporter_id,
            reason=reason,
            details=details,
            status="PENDING",
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def get(self, report_id: int) -> SkillReport | None:
        return await self._session.get(SkillReport, report_id)

    async def list_pending(self, *, limit: int, offset: int) -> tuple[list[SkillReport], int]:
        base = select(SkillReport).where(SkillReport.status == "PENDING")
        total = (
            await self._session.execute(select(func.count()).select_from(base.subquery()))
        ).scalar_one()
        stmt = base.order_by(SkillReport.created_at.desc()).offset(offset).limit(limit)
        rows = list((await self._session.execute(stmt)).scalars())
        return rows, total


class PromotionRequestRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        source_skill_id: int,
        source_version_id: int,
        target_namespace_id: int,
        submitted_by: str,
    ) -> PromotionRequest:
        row = PromotionRequest(
            source_skill_id=source_skill_id,
            source_version_id=source_version_id,
            target_namespace_id=target_namespace_id,
            status="PENDING",
            version=1,
            submitted_by=submitted_by,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def get(self, promotion_id: int) -> PromotionRequest | None:
        return await self._session.get(PromotionRequest, promotion_id)

    async def list_pending(self, *, limit: int, offset: int) -> tuple[list[PromotionRequest], int]:
        base = select(PromotionRequest).where(PromotionRequest.status == "PENDING")
        total = (
            await self._session.execute(select(func.count()).select_from(base.subquery()))
        ).scalar_one()
        stmt = base.order_by(PromotionRequest.submitted_at.desc()).offset(offset).limit(limit)
        rows = list((await self._session.execute(stmt)).scalars())
        return rows, total
