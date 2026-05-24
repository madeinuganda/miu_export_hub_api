from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TypeVar
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import AppError
from app.core.security import create_access_token, create_refresh_token, hash_refresh_token

settings = get_settings()
AccountT = TypeVar("AccountT")
SessionT = TypeVar("SessionT")


async def create_login_session(
    db: AsyncSession,
    *,
    account_id: UUID,
    account_type: str,
    session_cls: type[SessionT],
    account_id_field: str,
    user_agent: str | None,
    ip: str | None,
    actor_id: UUID,
) -> tuple[str, str]:
    refresh = create_refresh_token()
    session = session_cls(
        **{
            account_id_field: account_id,
            "refresh_token_hash": hash_refresh_token(refresh),
            "user_agent": user_agent,
            "ip_address": ip,
            "expires_at": datetime.now(timezone.utc) + timedelta(days=settings.jwt_refresh_expire_days),
            "created_by": actor_id,
            "updated_by": actor_id,
        }
    )
    db.add(session)
    access = create_access_token(account_id, account_type)
    return access, refresh


async def refresh_session(
    db: AsyncSession,
    *,
    refresh_token: str,
    account_type: str,
    session_cls: type[SessionT],
    account_cls: type[AccountT],
    account_id_field: str,
    session_account_fk: str,
) -> tuple[AccountT, str, str]:
    token_hash = hash_refresh_token(refresh_token)
    account_col = getattr(session_cls, account_id_field)
    result = await db.execute(
        select(session_cls, account_cls)
        .join(account_cls, getattr(account_cls, "id") == account_col)
        .where(
            session_cls.refresh_token_hash == token_hash,
            session_cls.revoked_at.is_(None),
            session_cls.deleted_at.is_(None),
            account_cls.deleted_at.is_(None),
        )
    )
    row = result.first()
    if not row:
        raise AppError(401, "Invalid refresh token", "invalid_refresh")
    session, account = row
    if session.expires_at < datetime.now(timezone.utc):
        raise AppError(401, "Refresh token expired", "refresh_expired")
    if not account.is_active:
        raise AppError(403, "Account disabled", "account_disabled")

    session.revoked_at = datetime.now(timezone.utc)
    account_id = getattr(account, "id")
    access, new_refresh = await create_login_session(
        db,
        account_id=account_id,
        account_type=account_type,
        session_cls=session_cls,
        account_id_field=account_id_field,
        user_agent=session.user_agent,
        ip=session.ip_address,
        actor_id=account_id,
    )
    return account, access, new_refresh


async def revoke_refresh_session(db: AsyncSession, session_cls: type[SessionT], refresh_token: str) -> None:
    token_hash = hash_refresh_token(refresh_token)
    result = await db.execute(select(session_cls).where(session_cls.refresh_token_hash == token_hash))
    session = result.scalar_one_or_none()
    if session:
        session.revoked_at = datetime.now(timezone.utc)


async def revoke_all_account_sessions(
    db: AsyncSession,
    session_cls: type[SessionT],
    account_id_field: str,
    account_id: UUID,
) -> None:
    now = datetime.now(timezone.utc)
    account_col = getattr(session_cls, account_id_field)
    result = await db.execute(
        select(session_cls).where(
            account_col == account_id,
            session_cls.revoked_at.is_(None),
            session_cls.deleted_at.is_(None),
        )
    )
    for session in result.scalars().all():
        session.revoked_at = now
