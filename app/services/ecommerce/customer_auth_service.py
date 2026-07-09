from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.shared.exceptions import AppError
from app.core.shared.security import hash_password, verify_password
from app.models.ecommerce.accounts import CustomerAccount, CustomerSession
from app.models.shared.enums import EcommerceAccountType, Platform
from app.schemas.export_hub.auth import LoginRequest
from app.schemas.ecommerce.auth import (
    CartMergeSummary,
    CustomerAccountSummary,
    CustomerAuthResponse,
    CustomerRegisterRequest,
)
from app.services.ecommerce.address_service import EcommerceAddressService
from app.services.ecommerce.cart_service import EcommerceCartService
from app.services.shared.auth_session import create_login_session, refresh_session, revoke_refresh_session
from app.utils.audit import apply_create_audit, apply_update_audit


class EcommerceCustomerAuthService:
    @staticmethod
    def _summary(account: CustomerAccount) -> CustomerAccountSummary:
        return CustomerAccountSummary(
            id=account.id,
            email=account.email,
            first_name=account.first_name,
            last_name=account.last_name,
            customer_type=account.customer_type,
            must_change_password=account.must_change_password,
            email_verified=account.email_verified_at is not None,
            wallet_balance=float(account.wallet_balance),
        )

    @staticmethod
    async def _merge_guest_cart_if_present(
        db: AsyncSession,
        guest_id: UUID | None,
        customer_id: UUID,
    ) -> CartMergeSummary | None:
        if not guest_id:
            return None
        merged_items = await EcommerceCartService.merge_guest_cart(db, guest_id, customer_id)
        merged_addresses = await EcommerceAddressService.merge_guest_addresses(
            db, guest_id, customer_id
        )
        return CartMergeSummary(
            guest_id=guest_id,
            merged_items=merged_items,
            merged_addresses=merged_addresses,
        )

    @staticmethod
    async def build_auth_response(
        account: CustomerAccount,
        access: str,
        refresh: str,
        cart_merge: CartMergeSummary | None = None,
    ) -> CustomerAuthResponse:
        return CustomerAuthResponse(
            access_token=access,
            refresh_token=refresh,
            account=EcommerceCustomerAuthService._summary(account),
            must_change_password=account.must_change_password,
            cart_merge=cart_merge,
        )

    @staticmethod
    async def register(db: AsyncSession, data: CustomerRegisterRequest) -> CustomerAuthResponse:
        existing = await db.execute(
            select(CustomerAccount).where(
                CustomerAccount.email == data.email,
                CustomerAccount.deleted_at.is_(None),
            )
        )
        if existing.scalar_one_or_none():
            raise AppError(409, "Email already registered", "email_taken")

        account = CustomerAccount(
            id=uuid4(),
            email=data.email,
            password_hash=hash_password(data.password),
            first_name=data.first_name,
            last_name=data.last_name,
            phone=data.phone,
            customer_type=data.customer_type,
            is_active=True,
            email_verified_at=datetime.now(timezone.utc),
        )
        apply_create_audit(account, account.id)
        db.add(account)
        await db.flush()
        access, refresh = await create_login_session(
            db,
            account_id=account.id,
            account_type=EcommerceAccountType.CUSTOMER.value,
            platform=Platform.ECOMMERCE.value,
            session_cls=CustomerSession,
            account_id_field="customer_account_id",
            user_agent=None,
            ip=None,
            actor_id=account.id,
        )
        cart_merge = await EcommerceCustomerAuthService._merge_guest_cart_if_present(
            db, data.guest_id, account.id
        )
        return await EcommerceCustomerAuthService.build_auth_response(
            account, access, refresh, cart_merge=cart_merge
        )

    @staticmethod
    async def login(
        db: AsyncSession,
        data: LoginRequest,
        user_agent: str | None,
        ip: str | None,
        guest_id: UUID | None = None,
    ) -> CustomerAuthResponse:
        result = await db.execute(
            select(CustomerAccount).where(
                CustomerAccount.email == data.email,
                CustomerAccount.deleted_at.is_(None),
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
            account_type=EcommerceAccountType.CUSTOMER.value,
            platform=Platform.ECOMMERCE.value,
            session_cls=CustomerSession,
            account_id_field="customer_account_id",
            user_agent=user_agent,
            ip=ip,
            actor_id=account.id,
        )
        cart_merge = await EcommerceCustomerAuthService._merge_guest_cart_if_present(
            db, guest_id, account.id
        )
        return await EcommerceCustomerAuthService.build_auth_response(
            account, access, refresh, cart_merge=cart_merge
        )

    @staticmethod
    async def refresh(db: AsyncSession, refresh_token: str) -> CustomerAuthResponse:
        account, access, new_refresh = await refresh_session(
            db,
            refresh_token=refresh_token,
            account_type=EcommerceAccountType.CUSTOMER.value,
            platform=Platform.ECOMMERCE.value,
            session_cls=CustomerSession,
            account_cls=CustomerAccount,
            account_id_field="customer_account_id",
            session_account_fk="customer_account_id",
        )
        return await EcommerceCustomerAuthService.build_auth_response(account, access, new_refresh)

    @staticmethod
    async def logout(db: AsyncSession, refresh_token: str) -> None:
        await revoke_refresh_session(db, CustomerSession, refresh_token)
