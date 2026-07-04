from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ecommerce.deps import CartOwnerContext, get_cart_owner, get_current_customer
from app.core.shared.config import get_settings
from app.core.shared.database import get_db
from app.core.shared.exceptions import AppError
from app.models.ecommerce.accounts import CustomerAccount
from app.models.ecommerce.orders import EcommercePaymentRequest
from app.schemas.ecommerce.order import (
    DigitalPaymentRequest,
    DigitalPaymentResponse,
    PlaceOrderResponse,
)
from app.services.ecommerce.order_service import EcommerceOrderService
from app.services.ecommerce.pesapal_service import PesapalService

router = APIRouter(tags=["E-Commerce · Orders & Payments"])


@router.get("/customer/order/place", response_model=PlaceOrderResponse)
async def place_order_cod(
    address_id: UUID | None = Query(None),
    order_note: str | None = Query(None),
    owner: CartOwnerContext = Depends(get_cart_owner),
    db: AsyncSession = Depends(get_db),
):
    """Cash on delivery — Laravel GET /customer/order/place parity."""
    result = await EcommerceOrderService.place_cod_order(
        db, owner, address_id=address_id, order_note=order_note
    )
    await db.commit()
    return PlaceOrderResponse(**result)


@router.get("/customer/order/details")
async def get_order_details(
    order_id: UUID = Query(..., alias="order_id"),
    owner: CartOwnerContext = Depends(get_cart_owner),
    db: AsyncSession = Depends(get_db),
):
    return await EcommerceOrderService.get_order_details(db, owner, order_id)


@router.get("/customer/order/list")
async def get_order_list(
    account: CustomerAccount = Depends(get_current_customer),
    db: AsyncSession = Depends(get_db),
):
    return await EcommerceOrderService.list_orders(db, account.id)


@router.get("/order/cancel-order")
async def cancel_order(
    order_id: UUID = Query(..., alias="order_id"),
    owner: CartOwnerContext = Depends(get_cart_owner),
    db: AsyncSession = Depends(get_db),
):
    message = await EcommerceOrderService.cancel_order(db, owner, order_id)
    await db.commit()
    return message


@router.post("/digital-payment/", response_model=DigitalPaymentResponse)
async def initiate_digital_payment(
    data: DigitalPaymentRequest,
    owner: CartOwnerContext = Depends(get_cart_owner),
    db: AsyncSession = Depends(get_db),
):
    settings = get_settings()
    if not settings.pesapal_enabled:
        raise AppError(503, "Pesapal is not configured", "pesapal_not_configured")
    if data.payment_method not in ("pesapal", "flutterwave"):
        raise AppError(400, "Unsupported payment method", "invalid_payment_method")

    email, name, phone = await EcommerceOrderService.resolve_payer(db, owner)
    email = data.payer_email or email
    name = data.payer_name or name
    phone = data.payer_phone or phone

    payment = await EcommerceOrderService.create_payment_request(
        db,
        owner,
        payer_email=email,
        payer_name=name,
        payer_phone=phone,
        address_id=data.address_id,
        order_note=data.order_note,
    )
    await db.commit()

    redirect_link = (
        f"{settings.api_base_url.rstrip('/')}/api/v1/ecommerce/payments/pesapal/pay"
        f"?payment_id={payment.id}"
    )
    return DigitalPaymentResponse(redirect_link=redirect_link, payment_id=payment.id)


@router.get("/payments/pesapal/pay")
async def pesapal_pay_redirect(
    payment_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
):
    payment = (
        await db.execute(
            select(EcommercePaymentRequest).where(
                EcommercePaymentRequest.id == payment_id,
                EcommercePaymentRequest.is_paid.is_(False),
                EcommercePaymentRequest.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if not payment:
        raise AppError(404, "Payment request not found", "payment_not_found")

    settings = get_settings()
    callback_url = (
        f"{settings.api_base_url.rstrip('/')}/api/v1/ecommerce/payments/pesapal/callback"
        f"?payment_id={payment.id}"
    )
    payer = payment.payer()
    redirect_url = await PesapalService.submit_order_request(
        payment_id=str(payment.id),
        amount=payment.payment_amount,
        currency=payment.currency_code,
        description=f"Order {payment.id}",
        callback_url=callback_url,
        payer=payer,
    )
    return RedirectResponse(url=redirect_url, status_code=302)


async def _process_pesapal_payment(
    db: AsyncSession,
    payment: EcommercePaymentRequest,
    order_tracking_id: str,
) -> bool:
    status_payload = await PesapalService.get_transaction_status(order_tracking_id)
    if PesapalService.is_payment_successful(
        status_payload, payment.payment_amount, payment.currency_code
    ):
        if not payment.is_paid:
            await EcommerceOrderService.fulfill_payment_request(
                db, payment, transaction_ref=order_tracking_id
            )
        return True
    return False


@router.get("/payments/pesapal/callback")
async def pesapal_callback(
    payment_id: UUID = Query(...),
    OrderTrackingId: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    settings = get_settings()
    payment = (
        await db.execute(
            select(EcommercePaymentRequest).where(
                EcommercePaymentRequest.id == payment_id,
                EcommercePaymentRequest.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if not payment:
        raise AppError(404, "Payment request not found", "payment_not_found")

    if not OrderTrackingId:
        return RedirectResponse(
            url=f"{settings.ecommerce_frontend_base_url}/checkout?status=failed",
            status_code=302,
        )

    success = await _process_pesapal_payment(db, payment, OrderTrackingId)
    await db.commit()
    if success:
        return RedirectResponse(
            url=f"{settings.ecommerce_frontend_base_url}/checkout/success?payment_id={payment.id}",
            status_code=302,
        )
    return RedirectResponse(
        url=f"{settings.ecommerce_frontend_base_url}/checkout?status=failed",
        status_code=302,
    )


@router.post("/payments/pesapal/ipn")
async def pesapal_ipn(
    payment_id: UUID | None = Query(None),
    OrderTrackingId: str | None = Query(None),
    OrderMerchantReference: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Pesapal IPN / notification endpoint (idempotent)."""
    if not OrderTrackingId:
        return {"status": 400, "message": "Missing OrderTrackingId"}

    ref = payment_id or OrderMerchantReference
    if not ref:
        return {"status": 400, "message": "Missing payment reference"}

    try:
        resolved_uuid = ref if isinstance(ref, UUID) else UUID(str(ref))
    except ValueError:
        return {"status": 400, "message": "Invalid payment reference"}

    payment = (
        await db.execute(
            select(EcommercePaymentRequest).where(
                EcommercePaymentRequest.id == resolved_uuid,
                EcommercePaymentRequest.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if not payment:
        return {"status": 404, "message": "Payment not found"}

    success = await _process_pesapal_payment(db, payment, OrderTrackingId)
    await db.commit()
    return {
        "status": 200 if success or payment.is_paid else 400,
        "message": "Payment processed" if success or payment.is_paid else "Payment not completed",
        "payment_id": str(payment.id),
    }
