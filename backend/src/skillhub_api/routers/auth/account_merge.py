"""Account merge routes."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, status
from pydantic import Field
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from skillhub_api.deps import Principal, db_session, get_current_principal
from skillhub_api.errors import ConflictError, DomainError, NotFoundError, UnauthorizedError
from skillhub_api.infra.db.models.auth import (
    AccountMergeRequest,
    ApiToken,
    UserRoleBinding,
)
from skillhub_api.infra.db.models.namespace import NamespaceMember
from skillhub_api.infra.db.models.user import IdentityBinding, LocalCredential, UserAccount
from skillhub_api.schemas.base import ApiModel

router = APIRouter(prefix="/api/v1/account/merge", tags=["auth"])


class MergeInitiateRequest(ApiModel):
    secondary_identifier: str = Field(min_length=1, max_length=256)


class MergeInitiateResponse(ApiModel):
    merge_request_id: int
    secondary_user_id: str
    verification_token: str
    expires_at: str


class MergeVerifyRequest(ApiModel):
    merge_request_id: int
    verification_token: str = Field(min_length=1)


class MergeConfirmRequest(ApiModel):
    merge_request_id: int


class MessageResponse(ApiModel):
    message: str


async def _active_user(db: AsyncSession, user_id: str) -> UserAccount:
    user = await db.get(UserAccount, user_id)
    if user is None:
        raise NotFoundError("USER_NOT_FOUND", "user not found")
    if user.status != "ACTIVE":
        raise DomainError("USER_NOT_ACTIVE", "user must be active")
    return user


async def _secondary_user(db: AsyncSession, identifier: str) -> UserAccount:
    value = identifier.strip()
    if ":" in value:
        provider, subject = value.split(":", 1)
        binding = (
            await db.execute(
                select(IdentityBinding)
                .where(IdentityBinding.provider_code == provider)
                .where(IdentityBinding.subject == subject)
                .limit(1)
            )
        ).scalar_one_or_none()
        if binding is None:
            raise NotFoundError("SECONDARY_USER_NOT_FOUND", "secondary account not found")
        user = await db.get(UserAccount, binding.user_id)
    else:
        credential = (
            await db.execute(
                select(LocalCredential)
                .where(LocalCredential.username.ilike(value))
                .limit(1)
            )
        ).scalar_one_or_none()
        if credential is not None:
            user = await db.get(UserAccount, credential.user_id)
        else:
            user = (
                await db.execute(
                    select(UserAccount)
                    .where((UserAccount.id == value) | (UserAccount.email == value))
                    .limit(1)
                )
            ).scalar_one_or_none()
    if user is None:
        raise NotFoundError("SECONDARY_USER_NOT_FOUND", "secondary account not found")
    if user.status != "ACTIVE":
        raise DomainError("SECONDARY_USER_NOT_ACTIVE", "secondary account must be active")
    return user


async def _has_local_credential(db: AsyncSession, user_id: str) -> bool:
    row = (
        await db.execute(
            select(LocalCredential.id).where(LocalCredential.user_id == user_id).limit(1)
        )
    ).scalar_one_or_none()
    return row is not None


async def _request_for_primary(
    db: AsyncSession, request_id: int, primary_user_id: str
) -> AccountMergeRequest:
    row = (
        await db.execute(
            select(AccountMergeRequest)
            .where(AccountMergeRequest.id == request_id)
            .where(AccountMergeRequest.primary_user_id == primary_user_id)
            .limit(1)
        )
    ).scalar_one_or_none()
    if row is None:
        raise NotFoundError("MERGE_REQUEST_NOT_FOUND", "merge request not found")
    return row


@router.post("/initiate", response_model=MergeInitiateResponse, status_code=status.HTTP_201_CREATED)
async def initiate_merge(
    body: MergeInitiateRequest,
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(db_session),
) -> MergeInitiateResponse:
    primary = await _active_user(db, principal.user_id)
    secondary = await _secondary_user(db, body.secondary_identifier)
    if primary.id == secondary.id:
        raise DomainError("MERGE_SAME_ACCOUNT", "cannot merge an account into itself")
    pending = (
        await db.execute(
            select(AccountMergeRequest)
            .where(AccountMergeRequest.secondary_user_id == secondary.id)
            .where(AccountMergeRequest.status == "PENDING")
            .limit(1)
        )
    ).scalar_one_or_none()
    if pending is not None:
        raise ConflictError("MERGE_PENDING_EXISTS", "secondary account already has a pending merge")
    if await _has_local_credential(db, primary.id) and await _has_local_credential(db, secondary.id):
        raise ConflictError(
            "MERGE_LOCAL_CREDENTIAL_CONFLICT",
            "both accounts have local credentials; merge would create a login conflict",
        )
    token = secrets.token_urlsafe(24)
    expires_at = datetime.now(UTC) + timedelta(minutes=30)
    row = AccountMergeRequest(
        primary_user_id=primary.id,
        secondary_user_id=secondary.id,
        status="PENDING",
        verification_token=token,
        token_expires_at=expires_at,
    )
    db.add(row)
    await db.commit()
    return MergeInitiateResponse(
        merge_request_id=row.id,
        secondary_user_id=secondary.id,
        verification_token=token,
        expires_at=expires_at.isoformat().replace("+00:00", "Z"),
    )


@router.post("/verify", response_model=MessageResponse)
async def verify_merge(
    body: MergeVerifyRequest,
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(db_session),
) -> MessageResponse:
    row = await _request_for_primary(db, body.merge_request_id, principal.user_id)
    if row.status != "PENDING":
        raise DomainError("MERGE_NOT_PENDING", "merge request is not pending")
    if row.token_expires_at is None or row.token_expires_at < datetime.now(UTC):
        raise DomainError("MERGE_TOKEN_EXPIRED", "merge token expired")
    if not row.verification_token or not secrets.compare_digest(
        row.verification_token, body.verification_token
    ):
        raise UnauthorizedError("MERGE_TOKEN_INVALID", "invalid merge token")
    await _active_user(db, row.primary_user_id)
    await _active_user(db, row.secondary_user_id)
    row.status = "VERIFIED"
    await db.commit()
    return MessageResponse(message="Account merge verified")


@router.post("/confirm", response_model=MessageResponse)
async def confirm_merge(
    body: MergeConfirmRequest,
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(db_session),
) -> MessageResponse:
    row = await _request_for_primary(db, body.merge_request_id, principal.user_id)
    if row.status != "VERIFIED":
        raise DomainError("MERGE_NOT_VERIFIED", "merge request must be verified first")
    primary = await _active_user(db, row.primary_user_id)
    secondary = await _active_user(db, row.secondary_user_id)
    if await _has_local_credential(db, primary.id) and await _has_local_credential(db, secondary.id):
        raise ConflictError("MERGE_LOCAL_CREDENTIAL_CONFLICT", "both accounts have local credentials")

    await db.execute(
        update(IdentityBinding)
        .where(IdentityBinding.user_id == secondary.id)
        .values(user_id=primary.id)
    )
    await db.execute(
        update(ApiToken)
        .where(ApiToken.user_id == secondary.id)
        .values(user_id=primary.id, subject_id=primary.id)
    )
    secondary_roles = list(
        (
            await db.execute(
                select(UserRoleBinding.role_id).where(UserRoleBinding.user_id == secondary.id)
            )
        ).scalars()
    )
    primary_roles = set(
        (
            await db.execute(
                select(UserRoleBinding.role_id).where(UserRoleBinding.user_id == primary.id)
            )
        ).scalars()
    )
    for role_id in secondary_roles:
        if role_id not in primary_roles:
            db.add(UserRoleBinding(user_id=primary.id, role_id=role_id))
    await db.execute(delete(UserRoleBinding).where(UserRoleBinding.user_id == secondary.id))

    secondary_memberships = list(
        (
            await db.execute(
                select(NamespaceMember).where(NamespaceMember.user_id == secondary.id)
            )
        ).scalars()
    )
    role_rank = {"MEMBER": 0, "ADMIN": 1, "OWNER": 2}
    for membership in secondary_memberships:
        primary_membership = (
            await db.execute(
                select(NamespaceMember)
                .where(NamespaceMember.namespace_id == membership.namespace_id)
                .where(NamespaceMember.user_id == primary.id)
                .limit(1)
            )
        ).scalar_one_or_none()
        if primary_membership is None:
            membership.user_id = primary.id
        else:
            if role_rank.get(membership.role, 0) > role_rank.get(primary_membership.role, 0):
                primary_membership.role = membership.role
            await db.delete(membership)

    await db.execute(
        update(LocalCredential)
        .where(LocalCredential.user_id == secondary.id)
        .values(user_id=primary.id)
    )
    if not primary.email and secondary.email:
        primary.email = secondary.email
    secondary.status = "MERGED"
    secondary.merged_to_user_id = primary.id
    row.status = "COMPLETED"
    row.completed_at = datetime.now(UTC)
    row.verification_token = None
    await db.commit()
    return MessageResponse(message="Account merge completed")
