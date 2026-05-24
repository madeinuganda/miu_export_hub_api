from __future__ import annotations

from uuid import UUID

from fastapi import Depends, Header
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.exceptions import AppError
from app.core.security import decode_access_token
from app.core.security_schemes import BearerCredentials, http_bearer, http_bearer_refresh
from app.models.accounts import AdminAccount, BuyerAccount, SupplierAccount
from app.models.enums import VerificationStatus
from app.models.organizations import (
    BuyerOrganization,
    BuyerOrganizationMember,
    SupplierOrganization,
    SupplierOrganizationMember,
)


async def get_bearer_token(credentials: BearerCredentials | None = Depends(http_bearer)) -> str:
    if not credentials or credentials.scheme.lower() != "bearer":
        raise AppError(401, "Missing or invalid Authorization header", "unauthorized")
    return credentials.credentials


async def get_optional_bearer_token(
    credentials: BearerCredentials | None = Depends(http_bearer),
) -> str | None:
    if not credentials or credentials.scheme.lower() != "bearer":
        return None
    return credentials.credentials


async def get_refresh_bearer_token(
    credentials: BearerCredentials | None = Depends(http_bearer_refresh),
) -> str:
    if not credentials or credentials.scheme.lower() != "bearer":
        raise AppError(401, "Missing or invalid Authorization header (refresh token)", "unauthorized")
    return credentials.credentials


def _decode_account_id(token: str, expected_type: str) -> UUID:
    payload = decode_access_token(token)
    if not payload or not payload.get("sub"):
        raise AppError(401, "Invalid or expired token", "unauthorized")
    account_type = payload.get("account_type")
    if account_type != expected_type:
        if expected_type == "admin" and account_type in ("buyer", "supplier"):
            raise AppError(403, "Admin access required", "forbidden")
        raise AppError(401, "Token not valid for this portal", "wrong_account_type")
    return UUID(payload["sub"])


async def get_current_buyer(
    token: str = Depends(get_bearer_token),
    db: AsyncSession = Depends(get_db),
) -> BuyerAccount:
    account_id = _decode_account_id(token, "buyer")
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
    account_id = _decode_account_id(token, "supplier")
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
    account_id = _decode_account_id(token, "admin")
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
    """
    Allow sending via X-Notifications-Key (service-to-service) or admin bearer token.
    Returns AdminAccount when authenticated as admin; None when using API key.
    """
    settings = get_settings()
    if settings.notifications_api_key and x_notifications_key == settings.notifications_api_key:
        return None

    if not token:
        raise AppError(
            401,
            "Provide X-Notifications-Key or admin Bearer token",
            "unauthorized",
        )

    account_id = _decode_account_id(token, "admin")
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
