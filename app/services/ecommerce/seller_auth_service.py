from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.shared.exceptions import AppError
from app.core.shared.security import verify_password
from app.models.ecommerce.accounts import EcommerceShop, SellerAccount, SellerSession
from app.models.shared.enums import EcommerceAccountType, Platform
from app.schemas.export_hub.auth import LoginRequest
from app.schemas.ecommerce.seller import (
    SellerAccountSummary,
    SellerAuthResponse,
    SellerShopSummary,
)
from app.services.shared.auth_session import create_login_session, refresh_session, revoke_refresh_session


class EcommerceSellerAuthService:
    @staticmethod
    def _summary(account: SellerAccount) -> SellerAccountSummary:
        return SellerAccountSummary(
            id=account.id,
            email=account.email,
            first_name=account.first_name,
            last_name=account.last_name,
            must_change_password=account.must_change_password,
            email_verified=account.email_verified_at is not None,
        )

    @staticmethod
    def _shop_summary(shop: EcommerceShop | None) -> SellerShopSummary | None:
        if not shop:
            return None
        return SellerShopSummary(
            id=shop.id,
            name=shop.name,
            slug=shop.slug,
            is_published=shop.is_published,
        )

    @staticmethod
    async def _load_shop(db: AsyncSession, seller_id) -> EcommerceShop | None:
        return (
            await db.execute(
                select(EcommerceShop).where(
                    EcommerceShop.seller_account_id == seller_id,
                    EcommerceShop.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()

    @staticmethod
    async def build_auth_response(
        account: SellerAccount,
        shop: EcommerceShop | None,
        access: str,
        refresh: str,
    ) -> SellerAuthResponse:
        return SellerAuthResponse(
            access_token=access,
            refresh_token=refresh,
            account=EcommerceSellerAuthService._summary(account),
            shop=EcommerceSellerAuthService._shop_summary(shop),
            must_change_password=account.must_change_password,
        )

    @staticmethod
    async def login(
        db: AsyncSession,
        data: LoginRequest,
        user_agent: str | None,
        ip: str | None,
    ) -> SellerAuthResponse:
        account = (
            await db.execute(
                select(SellerAccount).where(
                    SellerAccount.email == data.email,
                    SellerAccount.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if not account or not verify_password(data.password, account.password_hash):
            raise AppError(401, "Invalid email or password", "invalid_credentials")
        if not account.is_active:
            raise AppError(403, "Account disabled", "account_disabled")

        account.last_login_at = datetime.now(timezone.utc)
        shop = await EcommerceSellerAuthService._load_shop(db, account.id)
        access, refresh = await create_login_session(
            db,
            account_id=account.id,
            account_type=EcommerceAccountType.SELLER.value,
            platform=Platform.ECOMMERCE.value,
            session_cls=SellerSession,
            account_id_field="seller_account_id",
            user_agent=user_agent,
            ip=ip,
            actor_id=account.id,
        )
        return await EcommerceSellerAuthService.build_auth_response(account, shop, access, refresh)

    @staticmethod
    async def refresh(db: AsyncSession, refresh_token: str) -> SellerAuthResponse:
        account, access, new_refresh = await refresh_session(
            db,
            refresh_token=refresh_token,
            account_type=EcommerceAccountType.SELLER.value,
            platform=Platform.ECOMMERCE.value,
            session_cls=SellerSession,
            account_cls=SellerAccount,
            account_id_field="seller_account_id",
            session_account_fk="seller_account_id",
        )
        shop = await EcommerceSellerAuthService._load_shop(db, account.id)
        return await EcommerceSellerAuthService.build_auth_response(
            account, shop, access, new_refresh
        )

    @staticmethod
    async def logout(db: AsyncSession, refresh_token: str) -> None:
        await revoke_refresh_session(db, SellerSession, refresh_token)
