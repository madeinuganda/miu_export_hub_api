from __future__ import annotations

from uuid import UUID

from fastapi import Depends, Header
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.shared.config import get_settings
from app.core.shared.database import get_db
from app.core.shared.deps import get_bearer_token, get_optional_bearer_token
from app.core.shared.exceptions import AppError
from app.core.shared.tokens import decode_realm_account_id
from app.models.export_hub.accounts import AdminAccount, BuyerAccount, SupplierAccount
from app.models.export_hub.organizations import (
    BuyerOrganization,
    BuyerOrganizationMember,
    SupplierOrganization,
    SupplierOrganizationMember,
)
from app.models.shared.enums import Platform, VerificationStatus


def _decode_export_hub_account_id(token: str, expected_type: str) -> UUID:
    return decode_realm_account_id(
        token,
        expected_type,
        expected_platform=Platform.EXPORT_HUB.value,
        legacy_missing_platform=True,
    )


async def get_current_buyer(
    token: str = Depends(get_bearer_token),
    db: AsyncSession = Depends(get_db),
) -> BuyerAccount:
    account_id = _decode_export_hub_account_id(token, "buyer")
    result = await db.execute(
        select(BuyerAccount).where(
            BuyerAccount.id == account_id,
            BuyerAccount.deleted_at.is_(None),
            BuyerAccount.is_active.is_(True),
        )
    )
    account = result.scalar_one_or_none()
    if not account:
        raise AppError(401, "Buyer account not found", "unauthorized")
    return account


async def get_current_supplier(
    token: str = Depends(get_bearer_token),
    db: AsyncSession = Depends(get_db),
) -> SupplierAccount:
    account_id = _decode_export_hub_account_id(token, "supplier")
    result = await db.execute(
        select(SupplierAccount).where(
            SupplierAccount.id == account_id,
            SupplierAccount.deleted_at.is_(None),
            SupplierAccount.is_active.is_(True),
        )
    )
    account = result.scalar_one_or_none()
    if not account:
        raise AppError(401, "Supplier account not found", "unauthorized")
    return account


async def get_current_admin(
    token: str = Depends(get_bearer_token),
    db: AsyncSession = Depends(get_db),
) -> AdminAccount:
    account_id = _decode_export_hub_account_id(token, "admin")
    result = await db.execute(
        select(AdminAccount).where(
            AdminAccount.id == account_id,
            AdminAccount.deleted_at.is_(None),
            AdminAccount.is_active.is_(True),
        )
    )
    account = result.scalar_one_or_none()
    if not account:
        raise AppError(401, "Admin account not found", "unauthorized")
    return account


async def require_buyer_password_changed(
    account: BuyerAccount = Depends(get_current_buyer),
) -> BuyerAccount:
    if account.must_change_password:
        raise AppError(
            403,
            "You must set a new password before continuing. Use POST /auth/buyer/change-password.",
            "password_change_required",
        )
    return account


async def require_supplier_password_changed(
    account: SupplierAccount = Depends(get_current_supplier),
) -> SupplierAccount:
    if account.must_change_password:
        raise AppError(
            403,
            "You must set a new password before continuing. Use POST /auth/supplier/change-password.",
            "password_change_required",
        )
    return account


async def require_admin_password_changed(
    account: AdminAccount = Depends(get_current_admin),
) -> AdminAccount:
    if account.must_change_password:
        raise AppError(
            403,
            "You must set a new password before continuing. Use POST /auth/admin/change-password.",
            "password_change_required",
        )
    return account


async def get_buyer_org(
    account: BuyerAccount = Depends(require_buyer_password_changed),
    db: AsyncSession = Depends(get_db),
) -> BuyerOrganization:
    result = await db.execute(
        select(BuyerOrganization)
        .join(BuyerOrganizationMember, BuyerOrganizationMember.org_id == BuyerOrganization.id)
        .where(
            BuyerOrganizationMember.buyer_account_id == account.id,
            BuyerOrganizationMember.deleted_at.is_(None),
            BuyerOrganization.deleted_at.is_(None),
        )
    )
    org = result.scalar_one_or_none()
    if not org:
        raise AppError(403, "Buyer organization membership required", "no_org")
    return org


async def get_buyer_org_id(org: BuyerOrganization = Depends(get_buyer_org)) -> UUID:
    return org.id


async def require_verified_buyer(
    account: BuyerAccount = Depends(require_buyer_password_changed),
) -> BuyerAccount:
    if not account.email_verified_at:
        raise AppError(
            403,
            "Activate your account using the link sent to your email.",
            "activation_required",
        )
    return account


async def require_onboarded_buyer(
    account: BuyerAccount = Depends(require_verified_buyer),
    org: BuyerOrganization = Depends(get_buyer_org),
) -> BuyerOrganization:
    if org.onboarding_status != VerificationStatus.APPROVED:
        from app.utils.audit import apply_update_audit

        org.onboarding_status = VerificationStatus.APPROVED
        org.verified_buyer = True
        apply_update_audit(org, account.id)
    return org


async def require_onboarded_buyer_org_id(org: BuyerOrganization = Depends(require_onboarded_buyer)) -> UUID:
    return org.id


async def get_supplier_org(
    account: SupplierAccount = Depends(require_supplier_password_changed),
    db: AsyncSession = Depends(get_db),
) -> SupplierOrganization:
    result = await db.execute(
        select(SupplierOrganization)
        .join(SupplierOrganizationMember, SupplierOrganizationMember.org_id == SupplierOrganization.id)
        .where(
            SupplierOrganizationMember.supplier_account_id == account.id,
            SupplierOrganizationMember.deleted_at.is_(None),
            SupplierOrganization.deleted_at.is_(None),
        )
    )
    org = result.scalar_one_or_none()
    if not org:
        raise AppError(403, "Supplier organization required", "no_org")
    return org


async def require_approved_supplier(org: SupplierOrganization = Depends(get_supplier_org)) -> SupplierOrganization:
    if org.verification_status != VerificationStatus.APPROVED:
        raise AppError(403, "Supplier must be approved", "supplier_not_approved")
    return org


def set_audit_actor(actor_id: UUID | None) -> UUID | None:
    return actor_id


async def require_notifications_access(
    x_notifications_key: str | None = Header(None, alias="X-Notifications-Key"),
    token: str | None = Depends(get_optional_bearer_token),
    db: AsyncSession = Depends(get_db),
) -> AdminAccount | None:
    settings = get_settings()
    if settings.notifications_api_key and x_notifications_key == settings.notifications_api_key:
        return None

    if not token:
        raise AppError(
            401,
            "Provide X-Notifications-Key or admin Bearer token",
            "unauthorized",
        )

    account_id = _decode_export_hub_account_id(token, "admin")
    result = await db.execute(
        select(AdminAccount).where(
            AdminAccount.id == account_id,
            AdminAccount.deleted_at.is_(None),
            AdminAccount.is_active.is_(True),
        )
    )
    account = result.scalar_one_or_none()
    if not account:
        raise AppError(401, "Admin account not found", "unauthorized")
    if account.must_change_password:
        raise AppError(
            403,
            "You must set a new password before continuing. Use POST /auth/admin/change-password.",
            "password_change_required",
        )
    return account
