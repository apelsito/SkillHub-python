"""Review workflow service.

A ``PENDING`` ``review_task`` is created automatically on publish for
PUBLIC/NAMESPACE_ONLY skills (see Phase 3). Here we implement the
reviewer actions: approve (flips version → PUBLISHED, sets latest) and
reject (flips version → back to DRAFT with a reason).

``submit_review`` is exposed for the owner-initiated path: re-submit a
version after fixes, or submit a previously-private version for public
visibility.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from skillhub_api.domain.events import (
    ReviewApprovedEvent,
    ReviewRejectedEvent,
    ReviewSubmittedEvent,
)
from skillhub_api.errors import ConflictError, ForbiddenError, NotFoundError
from skillhub_api.events.bus import EventBus
from skillhub_api.infra.db.models.governance import ReviewTask
from skillhub_api.infra.db.models.skill import SkillVersion
from skillhub_api.infra.repositories.governance import ReviewTaskRepository
from skillhub_api.infra.repositories.skill import SkillRepository, SkillVersionRepository


class ReviewService:
    def __init__(self, session: AsyncSession, bus: EventBus) -> None:
        self._session = session
        self._bus = bus
        self._reviews = ReviewTaskRepository(session)
        self._skills = SkillRepository(session)
        self._versions = SkillVersionRepository(session)

    async def submit(
        self,
        *,
        skill_version_id: int,
        submitter_id: str,
    ) -> ReviewTask:
        version = await self._session.get(SkillVersion, skill_version_id)
        if version is None:
            raise NotFoundError("VERSION_NOT_FOUND", "version not found")
        skill = await self._skills.get(version.skill_id)
        if skill is None:  # pragma: no cover — FK guarantees
            raise NotFoundError("SKILL_NOT_FOUND", "skill not found")
        if skill.owner_id != submitter_id:
            raise ForbiddenError(
                "NOT_SKILL_OWNER", "only the owner can submit a version for review"
            )
        existing = await self._reviews.find_pending_for_version(skill_version_id)
        if existing is not None:
            raise ConflictError(
                "REVIEW_ALREADY_PENDING", "a review is already pending for this version"
            )
        version.status = "PENDING_REVIEW"
        task = await self._reviews.create(
            skill_version_id=skill_version_id,
            namespace_id=skill.namespace_id,
            submitted_by=submitter_id,
        )
        self._bus.enqueue(
            ReviewSubmittedEvent(
                occurred_at=datetime.now(UTC),
                skill_id=skill.id,
                version_id=skill_version_id,
                review_id=task.id,
                namespace_id=skill.namespace_id,
                submitter_id=submitter_id,
            )
        )
        return task

    async def approve(
        self, *, review_id: int, reviewer_id: str, comment: str | None = None
    ) -> ReviewTask:
        task = await self._load_pending(review_id)
        version = await self._session.get(SkillVersion, task.skill_version_id)
        if version is None:  # pragma: no cover — FK guarantees
            raise NotFoundError("VERSION_NOT_FOUND", "version not found")
        skill = await self._skills.get(version.skill_id)
        if skill is None:  # pragma: no cover
            raise NotFoundError("SKILL_NOT_FOUND", "skill not found")

        now = datetime.now(UTC)
        task.status = "APPROVED"
        task.reviewed_by = reviewer_id
        task.reviewed_at = now
        task.review_comment = comment

        await self._versions.mark_published(version, now)
        await self._skills.set_latest_version(skill, version.id)

        self._bus.enqueue(
            ReviewApprovedEvent(
                occurred_at=now,
                skill_id=skill.id,
                version_id=version.id,
                review_id=task.id,
                reviewer_id=reviewer_id,
                submitter_id=task.submitted_by,
            )
        )
        return task

    async def reject(self, *, review_id: int, reviewer_id: str, reason: str) -> ReviewTask:
        task = await self._load_pending(review_id)
        version = await self._session.get(SkillVersion, task.skill_version_id)
        if version is None:  # pragma: no cover
            raise NotFoundError("VERSION_NOT_FOUND", "version not found")

        now = datetime.now(UTC)
        task.status = "REJECTED"
        task.reviewed_by = reviewer_id
        task.reviewed_at = now
        task.review_comment = reason

        # Revert the version state so the owner can edit and resubmit.
        version.status = "DRAFT"

        self._bus.enqueue(
            ReviewRejectedEvent(
                occurred_at=now,
                skill_id=version.skill_id,
                version_id=version.id,
                review_id=task.id,
                reviewer_id=reviewer_id,
                submitter_id=task.submitted_by,
                reason=reason,
            )
        )
        return task

    async def _load_pending(self, review_id: int) -> ReviewTask:
        task = await self._reviews.get(review_id)
        if task is None:
            raise NotFoundError("REVIEW_NOT_FOUND", f"review {review_id} not found")
        if task.status != "PENDING":
            raise ConflictError("REVIEW_NOT_PENDING", f"review already {task.status}")
        return task

    async def list_pending(self, *, namespace_id: int | None, limit: int, offset: int):
        return await self._reviews.list_pending(
            namespace_id=namespace_id, limit=limit, offset=offset
        )

    async def list_mine(self, submitter_id: str, *, limit: int, offset: int):
        return await self._reviews.list_for_submitter(submitter_id, limit=limit, offset=offset)
