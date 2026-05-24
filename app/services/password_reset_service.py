from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import AppError
from app.core.security import hash_password
from app.models.accounts import (
    AdminAccount,
    AdminSession,
    BuyerAccount,
    BuyerSession,
    SupplierAccount,
    SupplierSession,
)
from app.models.misc import PasswordResetToken
from app.services.auth_session import revoke_all_account_sessions
from app.services.email_service import EmailService
from app.utils.audit import apply_create_audit, apply_update_audit

AccountType = Literal["buyer", "supplier", "admin"]

_RESET_PATHS: dict[AccountType, str] = {
    "buyer": "/reset-password/buyer",
    "supplier": "/reset-password/supplier",
    "admin": "/reset-password/admin",
}

_GENERIC_MESSAGE = (
    "If an account exists for this email, a password reset link has been sent."
)


class PasswordResetService:
    @staticmethod
    def _hash_token(raw: str) -> str:
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def _reset_url(account_type: AccountType, raw_token: str) -> str:
        settings = get_settings()
        base = settings.frontend_base_url.rstrip("/")
        path = _RESET_PATHS[account_type]
        return f"{base}{path}?token={raw_token}"

    @staticmethod
    async def _invalidate_pending(
        db: AsyncSession,
        *,
        account_type: AccountType,
        account_id: UUID,
    ) -> None:
        now = datetime.now(timezone.utc)
        await db.execute(
            update(PasswordResetToken)
            .where(
                PasswordResetToken.account_type == account_type,
                PasswordResetToken.account_id == account_id,
                PasswordResetToken.used_at.is_(None),
                PasswordResetToken.deleted_at.is_(None),
            )
            .values(used_at=now)
        )

    @staticmethod
    async def _lookup_account(
        db: AsyncSession,
        account_type: AccountType,
        email: str,
    ) -> BuyerAccount | SupplierAccount | AdminAccount | None:
        email = email.strip()
        if account_type == "buyer":
            cls = BuyerAccount
        elif account_type == "supplier":
            cls = SupplierAccount
        else:
            cls = AdminAccount

        return (
            await db.execute(
                select(cls).where(cls.email == email, cls.deleted_at.is_(None))
            )
        ).scalar_one_or_none()

    @staticmethod
    def _can_reset(account_type: AccountType, account: BuyerAccount | SupplierAccount | AdminAccount) -> bool:
        if not account.is_active:
            return False
        if account_type == "buyer" and not account.email_verified_at:
            return False
        return True

    @staticmethod
    async def request_reset(db: AsyncSession, *, account_type: AccountType, email: str) -> str:
        account = await PasswordResetService._lookup_account(db, account_type, email)
        if not account or not PasswordResetService._can_reset(account_type, account):
            return _GENERIC_MESSAGE

        settings = get_settings()
        await PasswordResetService._invalidate_pending(
            db, account_type=account_type, account_id=account.id
        )

        raw = secrets.token_urlsafe(32)
        row = PasswordResetToken(
            account_type=account_type,
            account_id=account.id,
            token_hash=PasswordResetService._hash_token(raw),
            expires_at=datetime.now(timezone.utc)
            + timedelta(hours=settings.password_reset_ttl_hours),
        )
        apply_create_audit(row, account.id)
        db.add(row)
        await db.flush()

        reset_url = PasswordResetService._reset_url(account_type, raw)
        await EmailService.send_password_reset_email(
            to_email=account.email,
            reset_url=reset_url,
            first_name=account.first_name,
            account_type=account_type,
        )
        return _GENERIC_MESSAGE

    @staticmethod
    async def reset_password(
        db: AsyncSession,
        *,
        account_type: AccountType,
        raw_token: str,
        new_password: str,
    ) -> None:
        if not raw_token or len(raw_token) < 16:
            raise AppError(400, "Invalid reset token", "invalid_token")

        token_hash = PasswordResetService._hash_token(raw_token)
        row = (
            await db.execute(
                select(PasswordResetToken).where(
                    PasswordResetToken.token_hash == token_hash,
                    PasswordResetToken.account_type == account_type,
                    PasswordResetToken.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()

        if not row or row.used_at:
            raise AppError(400, "Reset link is invalid or already used", "invalid_token")
        if row.expires_at < datetime.now(timezone.utc):
            raise AppError(400, "Reset link has expired", "token_expired")

        account = await PasswordResetService._get_account_by_id(db, account_type, row.account_id)
        if not account or account.deleted_at or not account.is_active:
            raise AppError(400, "Account not found", "invalid_token")

        account.password_hash = hash_password(new_password)
        account.must_change_password = False
        apply_update_audit(account, account.id)

        row.used_at = datetime.now(timezone.utc)
        apply_update_audit(row, account.id)

        session_map: dict[AccountType, tuple[type, str]] = {
            "buyer": (BuyerSession, "buyer_account_id"),
            "supplier": (SupplierSession, "supplier_account_id"),
            "admin": (AdminSession, "admin_account_id"),
        }
        session_cls, fk = session_map[account_type]
        await revoke_all_account_sessions(db, session_cls, fk, account.id)

    @staticmethod
    async def _get_account_by_id(
        db: AsyncSession,
        account_type: AccountType,
        account_id: UUID,
    ) -> BuyerAccount | SupplierAccount | AdminAccount | None:
        if account_type == "buyer":
            return await db.get(BuyerAccount, account_id)
        if account_type == "supplier":
            return await db.get(SupplierAccount, account_id)
        return await db.get(AdminAccount, account_id)
