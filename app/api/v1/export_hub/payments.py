from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.shared.database import get_db
from app.core.shared.exceptions import AppError
from app.models.export_hub.accounts import BuyerAccount
from app.models.export_hub.orders import Order
from app.models.export_hub.organizations import BuyerOrganizationMember
from app.models.export_hub.payments import PaymentEscrow, PaymentLink
from app.services.export_hub.payment_service import PaymentService

router = APIRouter(prefix="/payments")


@router.get("/pesapal/pay")
async def pesapal_pay_redirect(
    token: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    link = (
        await db.execute(
            select(PaymentLink).where(
                PaymentLink.token == token,
                PaymentLink.deleted_at.is_(None),
            ).limit(1)
        )
    ).scalar_one_or_none()
    if not link:
        raise AppError(404, "Payment link not found", "not_found")

    escrow = await db.get(PaymentEscrow, link.escrow_id)
    payer = {"email": "buyer@example.com", "name": "MIU Buyer", "phone": ""}
    if escrow:
        order = await db.get(Order, escrow.order_id)
        if order:
            buyer_account = (
                await db.execute(
                    select(BuyerAccount)
                    .join(
                        BuyerOrganizationMember,
                        BuyerOrganizationMember.account_id == BuyerAccount.id,
                    )
                    .where(
                        BuyerOrganizationMember.org_id == order.buyer_org_id,
                        BuyerAccount.deleted_at.is_(None),
                    )
                    .limit(1)
                )
            ).scalar_one_or_none()
            if buyer_account:
                payer = {
                    "email": buyer_account.email,
                    "name": f"{buyer_account.first_name} {buyer_account.last_name}".strip(),
                    "phone": buyer_account.phone or "",
                }

    redirect_url = await PaymentService.pesapal_pay_redirect(db, token, payer)
    return RedirectResponse(url=redirect_url, status_code=302)


@router.get("/pesapal/callback")
async def pesapal_callback(
    token: str = Query(...),
    OrderTrackingId: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    success, redirect_url = await PaymentService.process_pesapal_callback(
        db, token, OrderTrackingId
    )
    _ = success
    return RedirectResponse(url=redirect_url, status_code=302)
