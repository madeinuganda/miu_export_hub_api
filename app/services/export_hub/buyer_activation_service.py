from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.shared.config import get_settings
from app.core.shared.exceptions import AppError
from app.models.export_hub.accounts import BuyerAccount
from app.models.shared.enums import VerificationStatus
from app.models.export_hub.misc import AccountVerificationToken
from app.models.export_hub.organizations import BuyerOrganization, BuyerOrganizationMember
from app.services.shared.email_service import EmailService
from app.utils.audit import apply_create_audit, apply_update_audit


class BuyerActivationService:
    TOKEN_TTL_HOURS = 48

    @staticmethod
    def _hash_token(raw: str) -> str:
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @staticmethod
    async def create_and_send_activation(
        db: AsyncSession,
        account: BuyerAccount,
    ) -> None:
        raw = secrets.token_urlsafe(32)
        token = AccountVerificationToken(
            buyer_account_id=account.id,
            token_hash=BuyerActivationService._hash_token(raw),
            purpose="email_activation",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=BuyerActivationService.TOKEN_TTL_HOURS),
        )
        apply_create_audit(token, account.id)
        db.add(token)
        await db.flush()

        settings = get_settings()
        base = settings.frontend_base_url.rstrip("/")
        activation_url = f"{base}/register/buyer/activate?token={raw}"
        await EmailService.send_buyer_activation_email(
            to_email=account.email,
            activation_url=activation_url,
            first_name=account.first_name,
        )

    @staticmethod
    async def activate_account(db: AsyncSession, raw_token: str) -> BuyerAccount:
        if not raw_token or len(raw_token) < 16:
            raise AppError(400, "Invalid activation token", "invalid_token")

        token_hash = BuyerActivationService._hash_token(raw_token)
        row = (
            await db.execute(
                select(AccountVerificationToken).where(
                    AccountVerificationToken.token_hash == token_hash,
                    AccountVerificationToken.purpose == "email_activation",
                    AccountVerificationToken.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if not row or row.used_at:
            raise AppError(400, "Activation link is invalid or already used", "invalid_token")
        if row.expires_at < datetime.now(timezone.utc):
            raise AppError(400, "Activation link has expired", "token_expired")

        account = await db.get(BuyerAccount, row.buyer_account_id)
        if not account or account.deleted_at or not account.is_active:
            raise AppError(400, "Account not found", "invalid_token")

        account.email_verified_at = datetime.now(timezone.utc)
        apply_update_audit(account, account.id)

        org = (
            await db.execute(
                select(BuyerOrganization)
                .join(BuyerOrganizationMember, BuyerOrganizationMember.org_id == BuyerOrganization.id)
                .where(
                    BuyerOrganizationMember.buyer_account_id == account.id,
                    BuyerOrganizationMember.deleted_at.is_(None),
                    BuyerOrganization.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if org:
            org.onboarding_status = VerificationStatus.APPROVED
            org.verified_buyer = True
            org.onboarding_submitted_at = org.onboarding_submitted_at or datetime.now(timezone.utc)
            apply_update_audit(org, account.id)

        row.used_at = datetime.now(timezone.utc)
        apply_update_audit(row, account.id)
        return account

    @staticmethod
    async def resend_activation(db: AsyncSession, email: str) -> None:
        account = (
            await db.execute(
                select(BuyerAccount).where(
                    BuyerAccount.email == email,
                    BuyerAccount.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if not account:
            return
        if account.email_verified_at:
            return
        await BuyerActivationService.create_and_send_activation(db, account)
