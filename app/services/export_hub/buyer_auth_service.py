from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.shared.exceptions import AppError
from app.core.shared.security import hash_password, verify_password
from app.models.export_hub.accounts import BuyerAccount, BuyerSession
from app.models.shared.enums import OrgMemberRole, Platform, VerificationStatus
from app.models.export_hub.misc import BuyerRegistrationDraft
from app.models.export_hub.organizations import BuyerOrganization, BuyerOrganizationMember
from app.schemas.export_hub.auth import (
    BuyerAccountSummary,
    BuyerAuthResponse,
    BuyerRegisterRequest,
    BuyerRegisterResponse,
    LoginRequest,
)
from app.services.shared.auth_session import create_login_session, refresh_session, revoke_refresh_session
from app.services.export_hub.buyer_activation_service import BuyerActivationService
from app.utils.audit import apply_create_audit, apply_update_audit


class BuyerAuthService:
    @staticmethod
    def _summary(account: BuyerAccount) -> BuyerAccountSummary:
        return BuyerAccountSummary(
            id=account.id,
            email=account.email,
            first_name=account.first_name,
            last_name=account.last_name,
            must_change_password=account.must_change_password,
            email_verified=account.email_verified_at is not None,
        )

    @staticmethod
    def _activation_required(account: BuyerAccount) -> bool:
        return account.email_verified_at is None

    @staticmethod
    async def build_auth_response(
        db: AsyncSession, account: BuyerAccount, access: str, refresh: str
    ) -> BuyerAuthResponse:
        activation_required = BuyerAuthService._activation_required(account)
        return BuyerAuthResponse(
            access_token=access,
            refresh_token=refresh,
            account=BuyerAuthService._summary(account),
            onboarding_required=False,
            activation_required=activation_required,
            must_change_password=account.must_change_password,
        )

    @staticmethod
    async def register(db: AsyncSession, data: BuyerRegisterRequest) -> BuyerRegisterResponse:
        existing = await db.execute(
            select(BuyerAccount).where(BuyerAccount.email == data.email, BuyerAccount.deleted_at.is_(None))
        )
        if existing.scalar_one_or_none():
            raise AppError(409, "Email already registered", "email_taken")

        account = BuyerAccount(
            id=uuid4(),
            email=data.email,
            password_hash=hash_password(data.password),
            first_name=data.first_name,
            last_name=data.last_name,
            phone=data.phone,
            is_active=True,
            email_verified_at=None,
        )
        apply_create_audit(account, account.id)
        db.add(account)
        await db.flush()

        org = BuyerOrganization(
            name=data.company,
            country="",
            onboarding_status=VerificationStatus.DRAFT,
            verified_buyer=False,
        )
        apply_create_audit(org, account.id)
        db.add(org)
        await db.flush()
        db.add(
            BuyerOrganizationMember(
                org_id=org.id,
                buyer_account_id=account.id,
                role=OrgMemberRole.OWNER,
                created_by=account.id,
                updated_by=account.id,
            )
        )
        db.add(
            BuyerRegistrationDraft(
                buyer_account_id=account.id,
                step="company",
                payload={"company": {"company_name": data.company}},
                created_by=account.id,
                updated_by=account.id,
            )
        )
        await BuyerActivationService.create_and_send_activation(db, account)
        return BuyerRegisterResponse(
            message="Check your email for an activation link to access the buyer dashboard.",
            email=data.email,
        )

    @staticmethod
    async def activate_and_login(
        db: AsyncSession,
        raw_token: str,
        user_agent: str | None,
        ip: str | None,
    ) -> BuyerAuthResponse:
        account = await BuyerActivationService.activate_account(db, raw_token)
        account.last_login_at = datetime.now(timezone.utc)
        access, refresh = await create_login_session(
            db,
            account_id=account.id,
            account_type="buyer",
            platform=Platform.EXPORT_HUB.value,
            session_cls=BuyerSession,
            account_id_field="buyer_account_id",
            user_agent=user_agent,
            ip=ip,
            actor_id=account.id,
        )
        return await BuyerAuthService.build_auth_response(db, account, access, refresh)

    @staticmethod
    async def login(
        db: AsyncSession, data: LoginRequest, user_agent: str | None, ip: str | None
    ) -> BuyerAuthResponse:
        result = await db.execute(
            select(BuyerAccount).where(BuyerAccount.email == data.email, BuyerAccount.deleted_at.is_(None))
        )
        account = result.scalar_one_or_none()
        if not account or not verify_password(data.password, account.password_hash):
            raise AppError(401, "Invalid email or password", "invalid_credentials")
        if not account.is_active:
            raise AppError(403, "Account disabled", "account_disabled")
        if BuyerAuthService._activation_required(account):
            raise AppError(
                403,
                "Activate your account using the link sent to your email before signing in.",
                "activation_required",
            )

        account.last_login_at = datetime.now(timezone.utc)
        access, refresh = await create_login_session(
            db,
            account_id=account.id,
            account_type="buyer",
            platform=Platform.EXPORT_HUB.value,
            session_cls=BuyerSession,
            account_id_field="buyer_account_id",
            user_agent=user_agent,
            ip=ip,
            actor_id=account.id,
        )
        return await BuyerAuthService.build_auth_response(db, account, access, refresh)

    @staticmethod
    async def refresh(db: AsyncSession, refresh_token: str) -> BuyerAuthResponse:
        account, access, new_refresh = await refresh_session(
            db,
            refresh_token=refresh_token,
            account_type="buyer",
            platform=Platform.EXPORT_HUB.value,
            session_cls=BuyerSession,
            account_cls=BuyerAccount,
            account_id_field="buyer_account_id",
            session_account_fk="buyer_account_id",
        )
        if BuyerAuthService._activation_required(account):
            raise AppError(403, "Email activation required", "activation_required")
        return await BuyerAuthService.build_auth_response(db, account, access, new_refresh)

    @staticmethod
    async def logout(db: AsyncSession, refresh_token: str) -> None:
        await revoke_refresh_session(db, BuyerSession, refresh_token)

    @staticmethod
    async def change_password(
        db: AsyncSession, account: BuyerAccount, current_password: str, new_password: str
    ) -> None:
        if not verify_password(current_password, account.password_hash):
            raise AppError(400, "Current password is incorrect", "invalid_password")
        account.password_hash = hash_password(new_password)
        account.must_change_password = False
        apply_update_audit(account, account.id)
