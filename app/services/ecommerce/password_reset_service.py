from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.shared.config import get_settings
from app.core.shared.exceptions import AppError
from app.core.shared.security import hash_password, verify_password
from app.models.ecommerce.accounts import (
    CustomerAccount,
    CustomerSession,
    EcommerceAdminAccount,
    EcommerceAdminSession,
    SellerAccount,
    SellerSession,
)
from app.models.export_hub.misc import PasswordResetToken
from app.services.shared.auth_session import revoke_all_account_sessions
from app.services.shared.email_service import EmailService
from app.utils.audit import apply_create_audit, apply_update_audit

EcommerceResetType = Literal["ec_customer", "ec_seller", "ec_admin"]

_RESET_PATHS: dict[EcommerceResetType, str] = {
    "ec_customer": "/reset-password/customer",
    "ec_seller": "/reset-password/seller",
    "ec_admin": "/reset-password/shop-admin",
}

_GENERIC_MESSAGE = (
    "If an account exists for this email, a password reset link has been sent."
)


class EcommercePasswordResetService:
    @staticmethod
    def _hash_token(raw: str) -> str:
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def _reset_url(account_type: EcommerceResetType, raw_token: str) -> str:
        settings = get_settings()
        base = settings.ecommerce_frontend_base_url.rstrip("/")
        path = _RESET_PATHS[account_type]
        return f"{base}{path}?token={raw_token}"

    @staticmethod
    async def _lookup_account(
        db: AsyncSession,
        account_type: EcommerceResetType,
        email: str,
    ) -> CustomerAccount | SellerAccount | EcommerceAdminAccount | None:
        email = email.strip()
        if account_type == "ec_customer":
            cls = CustomerAccount
        elif account_type == "ec_seller":
            cls = SellerAccount
        else:
            cls = EcommerceAdminAccount
        return (
            await db.execute(
                select(cls).where(cls.email == email, cls.deleted_at.is_(None))
            )
        ).scalar_one_or_none()

    @staticmethod
    async def request_reset(
        db: AsyncSession, *, account_type: EcommerceResetType, email: str
    ) -> str:
        account = await EcommercePasswordResetService._lookup_account(db, account_type, email)
        if not account or not account.is_active:
            return _GENERIC_MESSAGE

        settings = get_settings()
        await db.execute(
            update(PasswordResetToken)
            .where(
                PasswordResetToken.account_type == account_type,
                PasswordResetToken.account_id == account.id,
                PasswordResetToken.used_at.is_(None),
                PasswordResetToken.deleted_at.is_(None),
            )
            .values(used_at=datetime.now(timezone.utc))
        )

        raw = secrets.token_urlsafe(32)
        row = PasswordResetToken(
            account_type=account_type,
            account_id=account.id,
            token_hash=EcommercePasswordResetService._hash_token(raw),
            expires_at=datetime.now(timezone.utc)
            + timedelta(hours=settings.password_reset_ttl_hours),
        )
        apply_create_audit(row, account.id)
        db.add(row)
        await db.flush()

        reset_url = EcommercePasswordResetService._reset_url(account_type, raw)
        portal = {
            "ec_customer": "Customer",
            "ec_seller": "Seller",
            "ec_admin": "Shop Admin",
        }[account_type]
        subject = f"Reset your MIU Shop {portal} password"
        body = (
            f"Hi {account.first_name},\n\n"
            f"Reset your password using this link:\n\n{reset_url}\n\n"
            f"This link expires in {settings.password_reset_ttl_hours} hour(s).\n"
        )
        try:
            from app.services.shared.notifications.email_delivery import EmailDeliveryService

            await EmailDeliveryService.send(to=account.email, subject=subject, body=body)
        except Exception:
            if settings.environment == "development":
                print(f"\n[MIU] E-commerce password reset for {account.email}:\n{reset_url}\n")
        return _GENERIC_MESSAGE

    @staticmethod
    async def reset_password(
        db: AsyncSession,
        *,
        account_type: EcommerceResetType,
        raw_token: str,
        new_password: str,
    ) -> None:
        if not raw_token or len(raw_token) < 16:
            raise AppError(400, "Invalid reset token", "invalid_token")

        token_hash = EcommercePasswordResetService._hash_token(raw_token)
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

        account = await EcommercePasswordResetService._get_account_by_id(
            db, account_type, row.account_id
        )
        if not account or account.deleted_at or not account.is_active:
            raise AppError(400, "Account not found", "invalid_token")

        account.password_hash = hash_password(new_password)
        account.must_change_password = False
        apply_update_audit(account, account.id)
        row.used_at = datetime.now(timezone.utc)
        apply_update_audit(row, account.id)

        session_map = {
            "ec_customer": (CustomerSession, "customer_account_id"),
            "ec_seller": (SellerSession, "seller_account_id"),
            "ec_admin": (EcommerceAdminSession, "ecommerce_admin_account_id"),
        }
        session_cls, fk = session_map[account_type]
        await revoke_all_account_sessions(db, session_cls, fk, account.id)

    @staticmethod
    async def _get_account_by_id(
        db: AsyncSession,
        account_type: EcommerceResetType,
        account_id: UUID,
    ) -> CustomerAccount | SellerAccount | EcommerceAdminAccount | None:
        if account_type == "ec_customer":
            return await db.get(CustomerAccount, account_id)
        if account_type == "ec_seller":
            return await db.get(SellerAccount, account_id)
        return await db.get(EcommerceAdminAccount, account_id)

    @staticmethod
    async def change_password(
        db: AsyncSession,
        account: CustomerAccount | SellerAccount | EcommerceAdminAccount,
        current_password: str,
        new_password: str,
        session_cls: type,
        session_fk: str,
    ) -> None:
        if not verify_password(current_password, account.password_hash):
            raise AppError(400, "Current password is incorrect", "invalid_password")
        account.password_hash = hash_password(new_password)
        account.must_change_password = False
        apply_update_audit(account, account.id)
