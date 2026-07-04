from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, Header, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.shared.database import get_db
from app.core.shared.deps import get_bearer_token, get_optional_bearer_token
from app.core.shared.exceptions import AppError
from app.core.shared.security import decode_token_context
from app.models.ecommerce.accounts import CustomerAccount, EcommerceAdminAccount, SellerAccount
from app.models.ecommerce.catalog import EcommerceGuest
from app.models.shared.enums import EcommerceAccountType, Platform


@dataclass(frozen=True)
class CartOwnerContext:
    owner_id: UUID
    is_guest: bool


async def get_cart_owner(
    guest_id: UUID | None = Query(None, description="Guest ID from GET /get-guest-id"),
    x_guest_id: UUID | None = Header(None, alias="X-Guest-Id"),
    token: str | None = Depends(get_optional_bearer_token),
    db: AsyncSession = Depends(get_db),
) -> CartOwnerContext:
    """Laravel apiGuestCheck parity: customer bearer OR guest_id."""
    if token:
        ctx = decode_token_context(
            token,
            expected_platform=Platform.ECOMMERCE.value,
            expected_account_type=EcommerceAccountType.CUSTOMER.value,
        )
        if ctx:
            account = (
                await db.execute(
                    select(CustomerAccount).where(
                        CustomerAccount.id == ctx.account_id,
                        CustomerAccount.deleted_at.is_(None),
                        CustomerAccount.is_active.is_(True),
                    )
                )
            ).scalar_one_or_none()
            if account:
                return CartOwnerContext(owner_id=account.id, is_guest=False)

    resolved_guest = guest_id or x_guest_id
    if resolved_guest:
        guest = (
            await db.execute(
                select(EcommerceGuest).where(
                    EcommerceGuest.id == resolved_guest,
                    EcommerceGuest.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if guest:
            return CartOwnerContext(owner_id=guest.id, is_guest=True)
        raise AppError(401, "Invalid guest_id", "invalid_guest")

    raise AppError(
        401,
        "Provide customer Bearer token or guest_id query param / X-Guest-Id header",
        "unauthorized",
    )


async def get_current_seller(
    token: str = Depends(get_bearer_token),
    db: AsyncSession = Depends(get_db),
) -> SellerAccount:
    ctx = decode_token_context(
        token,
        expected_platform=Platform.ECOMMERCE.value,
        expected_account_type=EcommerceAccountType.SELLER.value,
    )
    if not ctx:
        raise AppError(401, "Invalid or expired token", "unauthorized")

    result = await db.execute(
        select(SellerAccount).where(
            SellerAccount.id == ctx.account_id,
            SellerAccount.deleted_at.is_(None),
            SellerAccount.is_active.is_(True),
        )
    )
    account = result.scalar_one_or_none()
    if not account:
        raise AppError(401, "Seller account not found", "unauthorized")
    return account


async def require_seller_password_changed(
    account: SellerAccount = Depends(get_current_seller),
) -> SellerAccount:
    if account.must_change_password:
        raise AppError(
            403,
            "You must set a new password before continuing.",
            "password_change_required",
        )
    return account


async def get_current_customer(
    token: str = Depends(get_bearer_token),
    db: AsyncSession = Depends(get_db),
) -> CustomerAccount:
    ctx = decode_token_context(
        token,
        expected_platform=Platform.ECOMMERCE.value,
        expected_account_type=EcommerceAccountType.CUSTOMER.value,
    )
    if not ctx:
        raise AppError(401, "Invalid or expired token", "unauthorized")

    result = await db.execute(
        select(CustomerAccount).where(
            CustomerAccount.id == ctx.account_id,
            CustomerAccount.deleted_at.is_(None),
            CustomerAccount.is_active.is_(True),
        )
    )
    account = result.scalar_one_or_none()
    if not account:
        raise AppError(401, "Customer account not found", "unauthorized")
    return account


async def get_current_ecommerce_admin(
    token: str = Depends(get_bearer_token),
    db: AsyncSession = Depends(get_db),
) -> EcommerceAdminAccount:
    ctx = decode_token_context(
        token,
        expected_platform=Platform.ECOMMERCE.value,
        expected_account_type=EcommerceAccountType.ADMIN.value,
    )
    if not ctx:
        raise AppError(401, "Invalid or expired token", "unauthorized")

    result = await db.execute(
        select(EcommerceAdminAccount).where(
            EcommerceAdminAccount.id == ctx.account_id,
            EcommerceAdminAccount.deleted_at.is_(None),
            EcommerceAdminAccount.is_active.is_(True),
        )
    )
    account = result.scalar_one_or_none()
    if not account:
        raise AppError(401, "E-commerce admin account not found", "unauthorized")
    return account


async def require_customer_password_changed(
    account: CustomerAccount = Depends(get_current_customer),
) -> CustomerAccount:
    if account.must_change_password:
        raise AppError(
            403,
            "You must set a new password before continuing.",
            "password_change_required",
        )
    return account


async def require_ecommerce_admin_password_changed(
    account: EcommerceAdminAccount = Depends(get_current_ecommerce_admin),
) -> EcommerceAdminAccount:
    if account.must_change_password:
        raise AppError(
            403,
            "You must set a new password before continuing.",
            "password_change_required",
        )
    return account
