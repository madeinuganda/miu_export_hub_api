from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ecommerce.deps import (
    get_current_customer,
    get_current_ecommerce_admin,
    require_customer_password_changed,
    require_ecommerce_admin_password_changed,
    require_seller_password_changed,
)
from app.core.shared.database import get_db
from app.core.shared.deps import get_refresh_bearer_token
from app.models.ecommerce.accounts import CustomerAccount, EcommerceAdminAccount, SellerAccount
from app.schemas.shared.auth_common import LoginRequest
from app.schemas.ecommerce.auth import (
    CustomerAuthResponse,
    CustomerLoginRequest,
    CustomerMeResponse,
    CustomerRegisterRequest,
    EcommerceAdminAuthResponse,
    EcommerceAdminMeResponse,
)
from app.models.shared.enums import EcommerceAccountType, Platform
from app.schemas.ecommerce.seller import SellerAuthResponse, SellerMeResponse
from app.services.ecommerce.admin_auth_service import EcommerceAdminAuthService
from app.services.ecommerce.customer_auth_service import EcommerceCustomerAuthService
from app.services.ecommerce.seller_auth_service import EcommerceSellerAuthService
from app.services.shared.rbac_service import RbacService

router = APIRouter(prefix="/auth", tags=["E-Commerce · Auth"])


def _client_meta(request: Request) -> tuple[str | None, str | None]:
    return request.headers.get("user-agent"), request.client.host if request.client else None


@router.post("/customer/register", response_model=CustomerAuthResponse)
async def customer_register(data: CustomerRegisterRequest, db: AsyncSession = Depends(get_db)):
    """Register a retail or shop customer account (separate from Export Hub buyers)."""
    result = await EcommerceCustomerAuthService.register(db, data)
    await db.commit()
    return result


def _resolve_guest_id(body_guest_id: UUID | None, header_guest_id: UUID | None) -> UUID | None:
    return body_guest_id or header_guest_id


@router.post("/customer/login", response_model=CustomerAuthResponse)
async def customer_login(
    data: CustomerLoginRequest,
    request: Request,
    x_guest_id: UUID | None = Header(None, alias="X-Guest-Id"),
    db: AsyncSession = Depends(get_db),
):
    ua, ip = _client_meta(request)
    guest_id = _resolve_guest_id(data.guest_id, x_guest_id)
    result = await EcommerceCustomerAuthService.login(db, data, ua, ip, guest_id=guest_id)
    await db.commit()
    return result


@router.get("/customer/me", response_model=CustomerMeResponse)
async def customer_me(account: CustomerAccount = Depends(require_customer_password_changed)):
    return CustomerMeResponse(
        account=EcommerceCustomerAuthService._summary(account),
    )


@router.post("/customer/refresh", response_model=CustomerAuthResponse)
async def customer_refresh(
    refresh_token: str = Depends(get_refresh_bearer_token),
    db: AsyncSession = Depends(get_db),
):
    return await EcommerceCustomerAuthService.refresh(db, refresh_token)


@router.post("/customer/logout")
async def customer_logout(
    refresh_token: str = Depends(get_refresh_bearer_token),
    db: AsyncSession = Depends(get_db),
):
    await EcommerceCustomerAuthService.logout(db, refresh_token)
    return {"ok": True}


@router.post("/admin/login", response_model=EcommerceAdminAuthResponse)
async def ecommerce_admin_login(data: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    ua, ip = _client_meta(request)
    return await EcommerceAdminAuthService.login(db, data, ua, ip)


@router.get("/admin/me", response_model=EcommerceAdminMeResponse)
async def ecommerce_admin_me(
    account: EcommerceAdminAccount = Depends(require_ecommerce_admin_password_changed),
    db: AsyncSession = Depends(get_db),
):
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
    return EcommerceAdminMeResponse(
        account=EcommerceAdminAuthService._summary(account),
        roles=roles,
        permissions=sorted(permissions),
        role_label=roles[0] if roles else "E-Commerce Admin",
    )


@router.post("/admin/refresh", response_model=EcommerceAdminAuthResponse)
async def ecommerce_admin_refresh(
    refresh_token: str = Depends(get_refresh_bearer_token),
    db: AsyncSession = Depends(get_db),
):
    return await EcommerceAdminAuthService.refresh(db, refresh_token)


@router.post("/admin/logout")
async def ecommerce_admin_logout(
    refresh_token: str = Depends(get_refresh_bearer_token),
    db: AsyncSession = Depends(get_db),
):
    await EcommerceAdminAuthService.logout(db, refresh_token)
    return {"ok": True}


@router.post("/seller/login", response_model=SellerAuthResponse)
async def seller_login(data: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    ua, ip = _client_meta(request)
    result = await EcommerceSellerAuthService.login(db, data, ua, ip)
    await db.commit()
    return result


@router.get("/seller/me", response_model=SellerMeResponse)
async def seller_me(
    seller: SellerAccount = Depends(require_seller_password_changed),
    db: AsyncSession = Depends(get_db),
):
    shop = await EcommerceSellerAuthService._load_shop(db, seller.id)
    return SellerMeResponse(
        account=EcommerceSellerAuthService._summary(seller),
        shop=EcommerceSellerAuthService._shop_summary(shop),
    )


@router.post("/seller/refresh", response_model=SellerAuthResponse)
async def seller_refresh(
    refresh_token: str = Depends(get_refresh_bearer_token),
    db: AsyncSession = Depends(get_db),
):
    result = await EcommerceSellerAuthService.refresh(db, refresh_token)
    await db.commit()
    return result


@router.post("/seller/logout")
async def seller_logout(
    refresh_token: str = Depends(get_refresh_bearer_token),
    db: AsyncSession = Depends(get_db),
):
    await EcommerceSellerAuthService.logout(db, refresh_token)
    await db.commit()
    return {"ok": True}
