from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.shared.exceptions import AppError
from app.core.shared.security import verify_password
from app.models.ecommerce.accounts import EcommerceAdminAccount, EcommerceAdminSession
from app.models.shared.enums import EcommerceAccountType, Platform
from app.schemas.export_hub.auth import LoginRequest
from app.schemas.ecommerce.auth import (
    EcommerceAdminAccountSummary,
    EcommerceAdminAuthResponse,
)
from app.services.shared.auth_session import create_login_session, refresh_session, revoke_refresh_session
from app.services.shared.rbac_service import RbacService


class EcommerceAdminAuthService:
    @staticmethod
    def _summary(account: EcommerceAdminAccount) -> EcommerceAdminAccountSummary:
        return EcommerceAdminAccountSummary(
            id=account.id,
            email=account.email,
            first_name=account.first_name,
            last_name=account.last_name,
            must_change_password=account.must_change_password,
        )

    @staticmethod
    async def build_auth_response(
        db: AsyncSession, account: EcommerceAdminAccount, access: str, refresh: str
    ) -> EcommerceAdminAuthResponse:
        roles = await RbacService.get_roles(
            db,
            platform=Platform.ECOMMERCE,
            account_type=EcommerceAccountType.ADMIN.value,
            account_id=account.id,
        )
        permissions = await RbacService.get_permissions(
            db,
            platform=Platform.ECOMMERCE,
            account_type=EcommerceAccountType.ADMIN.value,
            account_id=account.id,
        )
        return EcommerceAdminAuthResponse(
            access_token=access,
            refresh_token=refresh,
            account=EcommerceAdminAuthService._summary(account),
            must_change_password=account.must_change_password,
            roles=roles,
            permissions=sorted(permissions),
        )

    @staticmethod
    async def login(
        db: AsyncSession, data: LoginRequest, user_agent: str | None, ip: str | None
    ) -> EcommerceAdminAuthResponse:
        result = await db.execute(
            select(EcommerceAdminAccount).where(
                EcommerceAdminAccount.email == data.email,
                EcommerceAdminAccount.deleted_at.is_(None),
            )
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
            account_type=EcommerceAccountType.ADMIN.value,
            platform=Platform.ECOMMERCE.value,
            session_cls=EcommerceAdminSession,
            account_id_field="ecommerce_admin_account_id",
            user_agent=user_agent,
            ip=ip,
            actor_id=account.id,
        )
        return await EcommerceAdminAuthService.build_auth_response(db, account, access, refresh)

    @staticmethod
    async def refresh(db: AsyncSession, refresh_token: str) -> EcommerceAdminAuthResponse:
        account, access, new_refresh = await refresh_session(
            db,
            refresh_token=refresh_token,
            account_type=EcommerceAccountType.ADMIN.value,
            platform=Platform.ECOMMERCE.value,
            session_cls=EcommerceAdminSession,
            account_cls=EcommerceAdminAccount,
            account_id_field="ecommerce_admin_account_id",
            session_account_fk="ecommerce_admin_account_id",
        )
        return await EcommerceAdminAuthService.build_auth_response(db, account, access, new_refresh)

    @staticmethod
    async def logout(db: AsyncSession, refresh_token: str) -> None:
        await revoke_refresh_session(db, EcommerceAdminSession, refresh_token)
