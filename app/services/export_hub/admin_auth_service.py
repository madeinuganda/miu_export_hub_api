from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.shared.exceptions import AppError
from app.core.shared.security import generate_temporary_password, hash_password, verify_password
from app.models.export_hub.accounts import AdminAccount, AdminSession
from app.models.shared.enums import EcommerceAccountType, ExportHubAccountType, Platform
from app.models.shared.rbac import AccountRoleAssignment, Role
from app.schemas.export_hub.auth import (
    AdminAccountSummary,
    AdminAuthResponse,
    AdminInviteRequest,
    AdminInviteResponse,
    LoginRequest,
)
from app.services.shared.auth_session import create_login_session, refresh_session, revoke_refresh_session
from app.services.shared.rbac_service import RbacService
from app.utils.audit import apply_create_audit, apply_update_audit

logger = logging.getLogger(__name__)


class AdminAuthService:
    @staticmethod
    def _summary(account: AdminAccount) -> AdminAccountSummary:
        return AdminAccountSummary(
            id=account.id,
            email=account.email,
            first_name=account.first_name,
            last_name=account.last_name,
            must_change_password=account.must_change_password,
        )

    @staticmethod
    async def build_auth_response(
        db: AsyncSession, account: AdminAccount, access: str, refresh: str
    ) -> AdminAuthResponse:
        roles = await RbacService.get_roles(
            db,
            platform=Platform.EXPORT_HUB,
            account_type=ExportHubAccountType.ADMIN.value,
            account_id=account.id,
        )
        permissions = await RbacService.get_permissions(
            db,
            platform=Platform.EXPORT_HUB,
            account_type=ExportHubAccountType.ADMIN.value,
            account_id=account.id,
        )
        return AdminAuthResponse(
            access_token=access,
            refresh_token=refresh,
            account=AdminAuthService._summary(account),
            must_change_password=account.must_change_password,
            platform=Platform.EXPORT_HUB.value,
            roles=roles,
            permissions=sorted(permissions),
        )

    @staticmethod
    async def invite(
        db: AsyncSession, inviter: AdminAccount, data: AdminInviteRequest
    ) -> AdminInviteResponse:
        existing = await db.execute(
            select(AdminAccount).where(AdminAccount.email == data.email, AdminAccount.deleted_at.is_(None))
        )
        if existing.scalar_one_or_none():
            raise AppError(409, "Email already registered", "email_taken")

        temp_password = generate_temporary_password()
        account = AdminAccount(
            id=uuid4(),
            email=data.email,
            password_hash=hash_password(temp_password),
            first_name=data.first_name,
            last_name=data.last_name,
            phone=data.phone,
            is_active=True,
            email_verified_at=datetime.now(timezone.utc),
            must_change_password=True,
            invited_at=datetime.now(timezone.utc),
            invited_by=inviter.id,
        )
        apply_create_audit(account, inviter.id)
        db.add(account)
        await db.flush()

        role_result = await db.execute(
            select(Role).where(
                Role.platform == Platform.EXPORT_HUB,
                Role.code == "export_hub.trade_admin",
                Role.deleted_at.is_(None),
            )
        )
        role = role_result.scalar_one_or_none()
        if role:
            db.add(
                AccountRoleAssignment(
                    platform=Platform.EXPORT_HUB,
                    account_type=ExportHubAccountType.ADMIN.value,
                    account_id=account.id,
                    role_id=role.id,
                    created_by=inviter.id,
                    updated_by=inviter.id,
                )
            )

        logger.info("Admin invite created for %s (account_id=%s)", account.email, account.id)
        return AdminInviteResponse(
            account_id=account.id,
            email=account.email,
            temporary_password=temp_password,
        )

    @staticmethod
    async def login(
        db: AsyncSession, data: LoginRequest, user_agent: str | None, ip: str | None
    ) -> AdminAuthResponse:
        result = await db.execute(
            select(AdminAccount).where(AdminAccount.email == data.email, AdminAccount.deleted_at.is_(None))
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
            account_type="admin",
            platform=Platform.EXPORT_HUB.value,
            session_cls=AdminSession,
            account_id_field="admin_account_id",
            user_agent=user_agent,
            ip=ip,
            actor_id=account.id,
        )
        return await AdminAuthService.build_auth_response(db, account, access, refresh)

    @staticmethod
    async def refresh(db: AsyncSession, refresh_token: str) -> AdminAuthResponse:
        account, access, new_refresh = await refresh_session(
            db,
            refresh_token=refresh_token,
            account_type="admin",
            platform=Platform.EXPORT_HUB.value,
            session_cls=AdminSession,
            account_cls=AdminAccount,
            account_id_field="admin_account_id",
            session_account_fk="admin_account_id",
        )
        return await AdminAuthService.build_auth_response(db, account, access, new_refresh)

    @staticmethod
    async def logout(db: AsyncSession, refresh_token: str) -> None:
        await revoke_refresh_session(db, AdminSession, refresh_token)

    @staticmethod
    async def change_password(
        db: AsyncSession, account: AdminAccount, current_password: str, new_password: str
    ) -> None:
        if not verify_password(current_password, account.password_hash):
            raise AppError(400, "Current password is incorrect", "invalid_password")
        account.password_hash = hash_password(new_password)
        account.must_change_password = False
        apply_update_audit(account, account.id)
