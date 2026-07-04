from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.shared.exceptions import AppError
from app.core.shared.security import hash_password, verify_password
from app.models.export_hub.accounts import SupplierAccount, SupplierSession
from app.models.shared.enums import OrgMemberRole, Platform, VerificationStatus
from app.models.export_hub.misc import SupplierRegistrationDraft
from app.models.export_hub.organizations import SupplierOrganization, SupplierOrganizationMember
from app.schemas.export_hub.auth import (
    LoginRequest,
    SupplierAccountSummary,
    SupplierAuthResponse,
    SupplierRegisterRequest,
)
from app.services.shared.auth_session import create_login_session, refresh_session, revoke_refresh_session
from app.utils.audit import apply_create_audit, apply_update_audit


class SupplierAuthService:
    @staticmethod
    def _summary(account: SupplierAccount) -> SupplierAccountSummary:
        return SupplierAccountSummary(
            id=account.id,
            email=account.email,
            first_name=account.first_name,
            last_name=account.last_name,
            must_change_password=account.must_change_password,
        )

    @staticmethod
    async def _onboarding_required(db: AsyncSession, account_id) -> bool:
        result = await db.execute(
            select(SupplierOrganization)
            .join(SupplierOrganizationMember, SupplierOrganizationMember.org_id == SupplierOrganization.id)
            .where(
                SupplierOrganizationMember.supplier_account_id == account_id,
                SupplierOrganization.deleted_at.is_(None),
            )
        )
        org = result.scalar_one_or_none()
        return org is not None and org.verification_status != VerificationStatus.APPROVED

    @staticmethod
    async def build_auth_response(
        db: AsyncSession, account: SupplierAccount, access: str, refresh: str
    ) -> SupplierAuthResponse:
        onboarding_required = await SupplierAuthService._onboarding_required(db, account.id)
        return SupplierAuthResponse(
            access_token=access,
            refresh_token=refresh,
            account=SupplierAuthService._summary(account),
            onboarding_required=onboarding_required,
            must_change_password=account.must_change_password,
        )

    @staticmethod
    async def register(db: AsyncSession, data: SupplierRegisterRequest) -> SupplierAccount:
        existing = await db.execute(
            select(SupplierAccount).where(SupplierAccount.email == data.email, SupplierAccount.deleted_at.is_(None))
        )
        if existing.scalar_one_or_none():
            raise AppError(409, "Email already registered", "email_taken")

        account = SupplierAccount(
            id=uuid4(),
            email=data.email,
            password_hash=hash_password(data.password),
            first_name=data.first_name,
            last_name=data.last_name,
            phone=data.phone,
            is_active=True,
            email_verified_at=datetime.now(timezone.utc),
        )
        apply_create_audit(account, account.id)
        db.add(account)
        await db.flush()

        slug = data.company.lower().replace(" ", "-")[:120]
        org = SupplierOrganization(
            name=data.company,
            slug=f"{slug}-{str(account.id)[:8]}",
            verification_status=VerificationStatus.DRAFT,
        )
        apply_create_audit(org, account.id)
        db.add(org)
        await db.flush()
        db.add(
            SupplierOrganizationMember(
                org_id=org.id,
                supplier_account_id=account.id,
                role=OrgMemberRole.OWNER,
                created_by=account.id,
                updated_by=account.id,
            )
        )
        db.add(
            SupplierRegistrationDraft(
                supplier_account_id=account.id,
                step="business",
                payload={"business": {"companyName": data.company}},
                created_by=account.id,
                updated_by=account.id,
            )
        )
        return account

    @staticmethod
    async def login(
        db: AsyncSession, data: LoginRequest, user_agent: str | None, ip: str | None
    ) -> SupplierAuthResponse:
        result = await db.execute(
            select(SupplierAccount).where(SupplierAccount.email == data.email, SupplierAccount.deleted_at.is_(None))
        )
        account = result.scalar_one_or_none()
        if not account or not verify_password(data.password, account.password_hash):
            raise AppError(401, "Invalid email or password", "invalid_credentials")
        if not account.is_active:
            raise AppError(403, "Account disabled", "account_disabled")

        account.last_login_at = datetime.now(timezone.utc)
        access, refresh = await create_login_session(
            db,
            account_id=account.id,
            account_type="supplier",
            platform=Platform.EXPORT_HUB.value,
            session_cls=SupplierSession,
            account_id_field="supplier_account_id",
            user_agent=user_agent,
            ip=ip,
            actor_id=account.id,
        )
        return await SupplierAuthService.build_auth_response(db, account, access, refresh)

    @staticmethod
    async def refresh(db: AsyncSession, refresh_token: str) -> SupplierAuthResponse:
        account, access, new_refresh = await refresh_session(
            db,
            refresh_token=refresh_token,
            account_type="supplier",
            platform=Platform.EXPORT_HUB.value,
            session_cls=SupplierSession,
            account_cls=SupplierAccount,
            account_id_field="supplier_account_id",
            session_account_fk="supplier_account_id",
        )
        return await SupplierAuthService.build_auth_response(db, account, access, new_refresh)

    @staticmethod
    async def logout(db: AsyncSession, refresh_token: str) -> None:
        await revoke_refresh_session(db, SupplierSession, refresh_token)

    @staticmethod
    async def change_password(
        db: AsyncSession, account: SupplierAccount, current_password: str, new_password: str
    ) -> None:
        if not verify_password(current_password, account.password_hash):
            raise AppError(400, "Current password is incorrect", "invalid_password")
        account.password_hash = hash_password(new_password)
        account.must_change_password = False
        apply_update_audit(account, account.id)
