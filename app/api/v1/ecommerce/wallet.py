from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ecommerce.deps import require_customer_password_changed
from app.core.shared.config import get_settings
from app.core.shared.database import get_db
from app.core.shared.exceptions import AppError
from app.models.ecommerce.accounts import CustomerAccount
from app.schemas.ecommerce.wallet import AddFundRequest, AddFundResponse, WalletConfigResponse
from app.services.ecommerce.wallet_service import EcommerceWalletService

router = APIRouter()


@router.get("/customer/wallet/list")
async def wallet_list(
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(1, ge=1),
    account: CustomerAccount = Depends(require_customer_password_changed),
    db: AsyncSession = Depends(get_db),
):
    return await EcommerceWalletService.list_transactions(
        db, account.id, limit=limit, offset=offset
    )


@router.get("/customer/wallet/config", response_model=WalletConfigResponse)
async def wallet_config():
    settings = get_settings()
    return WalletConfigResponse(
        wallet_enabled=settings.ecommerce_wallet_enabled,
        add_funds_enabled=settings.ecommerce_wallet_enabled,
        minimum_add_fund_amount=settings.ecommerce_wallet_min_add_fund,
        maximum_add_fund_amount=settings.ecommerce_wallet_max_add_fund,
        currency="UGX",
    )


@router.post("/add-to-fund/", response_model=AddFundResponse)
async def add_to_fund(
    data: AddFundRequest,
    account: CustomerAccount = Depends(require_customer_password_changed),
    db: AsyncSession = Depends(get_db),
):
    settings = get_settings()
    if not settings.pesapal_enabled:
        raise AppError(503, "Pesapal is not configured", "pesapal_not_configured")

    payment = await EcommerceWalletService.create_add_fund_request(
        db, account, Decimal(str(data.amount)), payment_method=data.payment_method
    )
    await db.commit()
    redirect_link = (
        f"{settings.api_base_url.rstrip('/')}/api/v1/ecommerce/payments/pesapal/pay"
        f"?payment_id={payment.id}"
    )
    return AddFundResponse(redirect_link=redirect_link, payment_id=payment.id)
