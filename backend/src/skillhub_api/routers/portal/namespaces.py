"""Namespace portal routes.

These mirror the Java ``NamespaceController`` under both ``/api/v1`` and
``/api/web``.  The frontend mostly consumes the ``/api/web`` aliases, while
CLI/back-office compatibility keeps ``/api/v1`` alive.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query, status
from pydantic import Field
from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from skillhub_api.deps import Principal, db_session, get_current_principal
from skillhub_api.errors import ConflictError, DomainError, ForbiddenError, NotFoundError
from skillhub_api.infra.db.models.auth import Role, UserRoleBinding
from skillhub_api.infra.db.models.namespace import Namespace, NamespaceMember
from skillhub_api.infra.db.models.user import UserAccount
from skillhub_api.schemas.base import ApiModel

router = APIRouter(prefix="/api/v1", tags=["namespaces"])

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$")
_ROLES = {"OWNER", "ADMIN", "MEMBER"}


class NamespaceRequest(ApiModel):
    slug: str | None = Field(default=None, max_length=64)
    display_name: str = Field(min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=2000)
    avatar_url: str | None = Field(default=None, max_length=512)


class NamespaceLifecycleRequest(ApiModel):
    reason: str | None = Field(default=None, max_length=2000)


class NamespaceResponse(ApiModel):
    id: int
    slug: str
    display_name: str
    status: str
    description: str | None = None
    type: str
    avatar_url: str | None = None
    created_by: str | None = None
    created_at: datetime
    updated_at: datetime | None = None


class ManagedNamespaceResponse(NamespaceResponse):
    current_user_role: str | None = None
    immutable: bool = False
    can_freeze: bool = False
    can_unfreeze: bool = False
    can_archive: bool = False
    can_restore: bool = False


class NamespacePage(ApiModel):
    items: list[NamespaceResponse]
    total: int
    page: int
    size: int
    limit: int
    offset: int


class MemberRequest(ApiModel):
    user_id: str = Field(min_length=1, max_length=128)
    role: str = Field(default="MEMBER", max_length=32)


class UpdateMemberRoleRequest(ApiModel):
    role: str = Field(max_length=32)


class BatchMemberRequest(ApiModel):
    members: list[MemberRequest]


class MemberResponse(ApiModel):
    id: int
    user_id: str
    display_name: str | None = None
    email: str | None = None
    role: str
    created_at: datetime


class MemberPage(ApiModel):
    items: list[MemberResponse]
    total: int
    page: int
    size: int
    limit: int
    offset: int


class NamespaceCandidateUserResponse(ApiModel):
    user_id: str
    display_name: str
    email: str | None = None
    status: str


class BatchMemberResult(ApiModel):
    user_id: str
    role: str
    success: bool
    error: str | None = None


class BatchMemberResponse(ApiModel):
    total_count: int
    success_count: int
    failure_count: int
    results: list[BatchMemberResult]


class MessageResponse(ApiModel):
    message: str


def _clean_slug(slug: str) -> str:
    value = slug.strip().lower()
    if value.startswith("@"):
        value = value[1:]
    if not _SLUG_RE.match(value):
        raise DomainError(
            "INVALID_NAMESPACE_SLUG",
            "namespace slug must be 3-64 lowercase letters, numbers, or hyphens",
            status.HTTP_400_BAD_REQUEST,
        )
    return value


def _role(value: str) -> str:
    role = value.strip().upper()
    if role not in _ROLES:
        raise DomainError("INVALID_NAMESPACE_ROLE", "role must be OWNER, ADMIN, or MEMBER")
    return role


def _dto(ns: Namespace) -> NamespaceResponse:
    return NamespaceResponse(
        id=ns.id,
        slug=ns.slug,
        display_name=ns.display_name,
        status=ns.status,
        description=ns.description,
        type=ns.type,
        avatar_url=ns.avatar_url,
        created_by=ns.created_by,
        created_at=ns.created_at,
        updated_at=ns.updated_at,
    )


async def _get_namespace(db: AsyncSession, slug: str) -> Namespace:
    row = (
        await db.execute(select(Namespace).where(Namespace.slug == _clean_slug(slug)).limit(1))
    ).scalar_one_or_none()
    if row is None:
        raise NotFoundError("NAMESPACE_NOT_FOUND", f"namespace {slug!r} not found")
    return row


async def _platform_roles(db: AsyncSession, user_id: str) -> set[str]:
    stmt = (
        select(Role.code)
        .join(UserRoleBinding, UserRoleBinding.role_id == Role.id)
        .where(UserRoleBinding.user_id == user_id)
    )
    return set((await db.execute(stmt)).scalars())


async def _member_role(db: AsyncSession, namespace_id: int, user_id: str) -> str | None:
    stmt = (
        select(NamespaceMember.role)
        .where(NamespaceMember.namespace_id == namespace_id)
        .where(NamespaceMember.user_id == user_id)
        .limit(1)
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def _can_manage(db: AsyncSession, ns: Namespace, user_id: str) -> bool:
    roles = await _platform_roles(db, user_id)
    if "SUPER_ADMIN" in roles or "NAMESPACE_ADMIN" in roles:
        return True
    role = await _member_role(db, ns.id, user_id)
    return role in {"OWNER", "ADMIN"}


async def _require_manage(db: AsyncSession, ns: Namespace, user_id: str) -> None:
    if not await _can_manage(db, ns, user_id):
        raise ForbiddenError("NAMESPACE_PERMISSION_DENIED", "namespace admin access required")


def _managed_dto(ns: Namespace, role: str | None, can_manage: bool) -> ManagedNamespaceResponse:
    immutable = ns.type == "GLOBAL"
    return ManagedNamespaceResponse(
        **_dto(ns).model_dump(),
        current_user_role=role,
        immutable=immutable,
        can_freeze=can_manage and ns.status == "ACTIVE" and not immutable,
        can_unfreeze=can_manage and ns.status == "FROZEN" and not immutable,
        can_archive=can_manage and ns.status != "ARCHIVED" and not immutable,
        can_restore=can_manage and ns.status == "ARCHIVED" and not immutable,
    )


@router.get("/namespaces", response_model=NamespacePage)
async def list_namespaces(
    page: int = Query(default=0, ge=0),
    size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(db_session),
) -> NamespacePage:
    base = select(Namespace)
    total = int((await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one())
    rows = list(
        (
            await db.execute(
                base.order_by(Namespace.type.asc(), Namespace.slug.asc())
                .offset(page * size)
                .limit(size)
            )
        ).scalars()
    )
    return NamespacePage(
        items=[_dto(row) for row in rows],
        total=total,
        page=page,
        size=size,
        limit=size,
        offset=page * size,
    )


@router.get("/namespaces/{slug}", response_model=NamespaceResponse)
async def get_namespace(slug: str, db: AsyncSession = Depends(db_session)) -> NamespaceResponse:
    return _dto(await _get_namespace(db, slug))


@router.post("/namespaces", response_model=NamespaceResponse, status_code=status.HTTP_201_CREATED)
async def create_namespace(
    body: NamespaceRequest,
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(db_session),
) -> NamespaceResponse:
    if not body.slug:
        raise DomainError("INVALID_NAMESPACE_SLUG", "namespace slug is required")
    ns = Namespace(
        slug=_clean_slug(body.slug),
        display_name=body.display_name.strip(),
        type="TEAM",
        description=body.description.strip() if body.description else None,
        avatar_url=body.avatar_url.strip() if body.avatar_url else None,
        status="ACTIVE",
        created_by=principal.user_id,
    )
    db.add(ns)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise ConflictError("NAMESPACE_EXISTS", "namespace slug already exists") from exc
    db.add(NamespaceMember(namespace_id=ns.id, user_id=principal.user_id, role="OWNER"))
    await db.commit()
    await db.refresh(ns)
    return _dto(ns)


@router.put("/namespaces/{slug}", response_model=NamespaceResponse)
async def update_namespace(
    slug: str,
    body: NamespaceRequest,
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(db_session),
) -> NamespaceResponse:
    ns = await _get_namespace(db, slug)
    await _require_manage(db, ns, principal.user_id)
    ns.display_name = body.display_name.strip()
    ns.description = body.description.strip() if body.description else None
    ns.avatar_url = body.avatar_url.strip() if body.avatar_url else None
    ns.updated_at = datetime.now(UTC)
    await db.commit()
    return _dto(ns)


async def _set_namespace_status(
    slug: str,
    next_status: str,
    principal: Principal,
    db: AsyncSession,
) -> NamespaceResponse:
    ns = await _get_namespace(db, slug)
    await _require_manage(db, ns, principal.user_id)
    if ns.type == "GLOBAL":
        raise ConflictError("NAMESPACE_IMMUTABLE", "global namespace cannot be modified")
    ns.status = next_status
    ns.updated_at = datetime.now(UTC)
    await db.commit()
    return _dto(ns)


@router.post("/namespaces/{slug}/freeze", response_model=NamespaceResponse)
async def freeze_namespace(
    slug: str,
    _body: NamespaceLifecycleRequest | None = None,
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(db_session),
) -> NamespaceResponse:
    return await _set_namespace_status(slug, "FROZEN", principal, db)


@router.post("/namespaces/{slug}/unfreeze", response_model=NamespaceResponse)
async def unfreeze_namespace(
    slug: str,
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(db_session),
) -> NamespaceResponse:
    return await _set_namespace_status(slug, "ACTIVE", principal, db)


@router.post("/namespaces/{slug}/archive", response_model=NamespaceResponse)
async def archive_namespace(
    slug: str,
    _body: NamespaceLifecycleRequest | None = None,
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(db_session),
) -> NamespaceResponse:
    return await _set_namespace_status(slug, "ARCHIVED", principal, db)


@router.post("/namespaces/{slug}/restore", response_model=NamespaceResponse)
async def restore_namespace(
    slug: str,
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(db_session),
) -> NamespaceResponse:
    return await _set_namespace_status(slug, "ACTIVE", principal, db)


@router.get("/namespaces/{slug}/members", response_model=MemberPage)
async def list_members(
    slug: str,
    page: int = Query(default=0, ge=0),
    size: int = Query(default=50, ge=1, le=100),
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(db_session),
) -> MemberPage:
    ns = await _get_namespace(db, slug)
    await _require_manage(db, ns, principal.user_id)
    base = (
        select(NamespaceMember, UserAccount)
        .join(UserAccount, UserAccount.id == NamespaceMember.user_id, isouter=True)
        .where(NamespaceMember.namespace_id == ns.id)
    )
    total = int((await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one())
    rows = list(
        (
            await db.execute(
                base.order_by(NamespaceMember.role.asc(), NamespaceMember.created_at.asc())
                .offset(page * size)
                .limit(size)
            )
        ).all()
    )
    return MemberPage(
        items=[
            MemberResponse(
                id=m.id,
                user_id=m.user_id,
                display_name=user.display_name if user else None,
                email=user.email if user else None,
                role=m.role,
                created_at=m.created_at,
            )
            for m, user in rows
        ],
        total=total,
        page=page,
        size=size,
        limit=size,
        offset=page * size,
    )


@router.get("/namespaces/{slug}/member-candidates", response_model=list[NamespaceCandidateUserResponse])
async def search_member_candidates(
    slug: str,
    search: str = Query(min_length=1),
    size: int = Query(default=10, ge=1, le=50),
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(db_session),
) -> list[NamespaceCandidateUserResponse]:
    ns = await _get_namespace(db, slug)
    await _require_manage(db, ns, principal.user_id)
    term = f"%{search.strip()}%"
    member_ids = select(NamespaceMember.user_id).where(NamespaceMember.namespace_id == ns.id)
    users = list(
        (
            await db.execute(
                select(UserAccount)
                .where(UserAccount.id.not_in(member_ids))
                .where(
                    or_(
                        UserAccount.id.ilike(term),
                        UserAccount.display_name.ilike(term),
                        UserAccount.email.ilike(term),
                    )
                )
                .order_by(UserAccount.display_name.asc())
                .limit(size)
            )
        ).scalars()
    )
    return [
        NamespaceCandidateUserResponse(
            user_id=user.id,
            display_name=user.display_name,
            email=user.email,
            status=user.status,
        )
        for user in users
    ]


async def _add_or_update_member(
    db: AsyncSession, ns: Namespace, user_id: str, role: str
) -> MemberResponse:
    user = await db.get(UserAccount, user_id)
    if user is None:
        raise NotFoundError("USER_NOT_FOUND", f"user {user_id!r} not found")
    clean_role = _role(role)
    row = (
        await db.execute(
            select(NamespaceMember)
            .where(NamespaceMember.namespace_id == ns.id)
            .where(NamespaceMember.user_id == user_id)
            .limit(1)
        )
    ).scalar_one_or_none()
    if row is None:
        row = NamespaceMember(namespace_id=ns.id, user_id=user_id, role=clean_role)
        db.add(row)
        await db.flush()
    else:
        row.role = clean_role
        row.updated_at = datetime.now(UTC)
        await db.flush()
    return MemberResponse(
        id=row.id,
        user_id=row.user_id,
        display_name=user.display_name,
        email=user.email,
        role=row.role,
        created_at=row.created_at,
    )


@router.post("/namespaces/{slug}/members", response_model=MemberResponse, status_code=status.HTTP_201_CREATED)
async def add_member(
    slug: str,
    body: MemberRequest,
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(db_session),
) -> MemberResponse:
    ns = await _get_namespace(db, slug)
    await _require_manage(db, ns, principal.user_id)
    result = await _add_or_update_member(db, ns, body.user_id, body.role)
    await db.commit()
    return result


@router.post("/namespaces/{slug}/members/batch", response_model=BatchMemberResponse)
async def batch_add_members(
    slug: str,
    body: BatchMemberRequest,
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(db_session),
) -> BatchMemberResponse:
    ns = await _get_namespace(db, slug)
    await _require_manage(db, ns, principal.user_id)
    results: list[BatchMemberResult] = []
    for item in body.members:
        try:
            await _add_or_update_member(db, ns, item.user_id, item.role)
            results.append(BatchMemberResult(user_id=item.user_id, role=_role(item.role), success=True))
        except DomainError as exc:
            results.append(
                BatchMemberResult(user_id=item.user_id, role=item.role, success=False, error=exc.message)
            )
    await db.commit()
    success_count = sum(1 for row in results if row.success)
    return BatchMemberResponse(
        total_count=len(results),
        success_count=success_count,
        failure_count=len(results) - success_count,
        results=results,
    )


@router.put("/namespaces/{slug}/members/{userId}/role", response_model=MemberResponse)
async def update_member_role(
    slug: str,
    userId: str,
    body: UpdateMemberRoleRequest,
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(db_session),
) -> MemberResponse:
    ns = await _get_namespace(db, slug)
    await _require_manage(db, ns, principal.user_id)
    result = await _add_or_update_member(db, ns, userId, body.role)
    await db.commit()
    return result


@router.delete("/namespaces/{slug}/members/{userId}", response_model=MessageResponse)
async def remove_member(
    slug: str,
    userId: str,
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(db_session),
) -> MessageResponse:
    ns = await _get_namespace(db, slug)
    await _require_manage(db, ns, principal.user_id)
    result = await db.execute(
        delete(NamespaceMember).where(
            NamespaceMember.namespace_id == ns.id,
            NamespaceMember.user_id == userId,
        )
    )
    await db.commit()
    if result.rowcount == 0:
        raise NotFoundError("MEMBER_NOT_FOUND", f"user {userId!r} is not a namespace member")
    return MessageResponse(message="Member removed")
