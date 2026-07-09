from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.shared.exceptions import AppError
from app.models.ecommerce.accounts import CustomerAccount, EcommerceShop
from app.models.ecommerce.orders import EcommerceOrder, EcommerceOrderItem
from app.models.shared.enums import EcommerceOrderStatus, EcommercePaymentStatus


class AdminOrderDashboardResponse(BaseModel):
    total_orders: int
    pending_orders: int
    paid_orders: int
    total_revenue: float
    currency: str = "UGX"
    by_status: dict[str, int]


class AdminOrderStatusUpdateRequest(BaseModel):
    order_status: str = Field(description="pending | confirmed | processing | out_for_delivery | delivered | canceled")


class EcommerceAdminOrderService:
    @staticmethod
    async def dashboard(db: AsyncSession) -> AdminOrderDashboardResponse:
        base = EcommerceOrder.deleted_at.is_(None)
        total = (
            await db.execute(select(func.count()).select_from(EcommerceOrder).where(base))
        ).scalar_one()

        pending = (
            await db.execute(
                select(func.count()).select_from(EcommerceOrder).where(
                    base,
                    EcommerceOrder.order_status == EcommerceOrderStatus.PENDING,
                )
            )
        ).scalar_one()

        paid = (
            await db.execute(
                select(func.count()).select_from(EcommerceOrder).where(
                    base,
                    EcommerceOrder.payment_status == EcommercePaymentStatus.PAID,
                )
            )
        ).scalar_one()

        revenue = (
            await db.execute(
                select(func.coalesce(func.sum(EcommerceOrder.paid_amount), 0)).where(
                    base,
                    EcommerceOrder.payment_status == EcommercePaymentStatus.PAID,
                )
            )
        ).scalar_one()

        status_rows = (
            await db.execute(
                select(EcommerceOrder.order_status, func.count())
                .where(base)
                .group_by(EcommerceOrder.order_status)
            )
        ).all()
        by_status = {status.value: count for status, count in status_rows}

        return AdminOrderDashboardResponse(
            total_orders=total,
            pending_orders=pending,
            paid_orders=paid,
            total_revenue=float(revenue or Decimal("0")),
            by_status=by_status,
        )

    @staticmethod
    async def list_orders(
        db: AsyncSession,
        *,
        status: str = "all",
        shop_id: UUID | None = None,
        limit: int = 20,
        offset: int = 1,
    ) -> dict:
        filters = [EcommerceOrder.deleted_at.is_(None)]
        if status != "all":
            try:
                filters.append(EcommerceOrder.order_status == EcommerceOrderStatus(status))
            except ValueError as exc:
                raise AppError(400, "Invalid order status filter", "invalid_status") from exc
        if shop_id:
            filters.append(EcommerceOrder.shop_id == shop_id)

        total = (
            await db.execute(
                select(func.count()).select_from(EcommerceOrder).where(*filters)
            )
        ).scalar_one()

        page = max(offset, 1)
        skip = (page - 1) * limit
        orders = (
            await db.execute(
                select(EcommerceOrder)
                .where(*filters)
                .order_by(EcommerceOrder.created_at.desc())
                .offset(skip)
                .limit(limit)
            )
        ).scalars().all()

        items = []
        for order in orders:
            shop = (
                await db.execute(
                    select(EcommerceShop).where(EcommerceShop.id == order.shop_id)
                )
            ).scalar_one_or_none()
            customer_email = None
            if order.customer_id:
                customer = (
                    await db.execute(
                        select(CustomerAccount).where(CustomerAccount.id == order.customer_id)
                    )
                ).scalar_one_or_none()
                customer_email = customer.email if customer else None

            items.append(
                {
                    "id": str(order.id),
                    "order_id": order.public_id,
                    "shop_id": str(order.shop_id),
                    "shop_name": shop.name if shop else None,
                    "customer_email": customer_email,
                    "is_guest": order.is_guest,
                    "order_status": order.order_status.value,
                    "payment_status": order.payment_status.value,
                    "payment_method": order.payment_method.value,
                    "order_amount": float(order.order_amount),
                    "paid_amount": float(order.paid_amount),
                    "created_at": order.created_at.isoformat(),
                }
            )

        return {"total_size": total, "limit": limit, "offset": page, "orders": items}

    @staticmethod
    async def order_detail(db: AsyncSession, order_id: UUID) -> dict:
        order = (
            await db.execute(
                select(EcommerceOrder).where(
                    EcommerceOrder.id == order_id,
                    EcommerceOrder.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if not order:
            raise AppError(404, "Order not found", "order_not_found")

        shop = (
            await db.execute(select(EcommerceShop).where(EcommerceShop.id == order.shop_id))
        ).scalar_one_or_none()
        items = (
            await db.execute(
                select(EcommerceOrderItem).where(
                    EcommerceOrderItem.order_id == order.id,
                    EcommerceOrderItem.deleted_at.is_(None),
                )
            )
        ).scalars().all()

        import json

        shipping_address = None
        if order.shipping_address_snapshot:
            try:
                shipping_address = json.loads(order.shipping_address_snapshot)
            except json.JSONDecodeError:
                shipping_address = order.shipping_address_snapshot

        return {
            "id": str(order.id),
            "order_id": order.public_id,
            "order_group_id": str(order.order_group_id),
            "shop": {"id": str(shop.id), "name": shop.name, "slug": shop.slug} if shop else None,
            "customer_id": str(order.customer_id) if order.customer_id else None,
            "guest_id": str(order.guest_id) if order.guest_id else None,
            "is_guest": order.is_guest,
            "order_status": order.order_status.value,
            "payment_status": order.payment_status.value,
            "payment_method": order.payment_method.value,
            "transaction_ref": order.transaction_ref,
            "order_amount": float(order.order_amount),
            "shipping_cost": float(order.shipping_cost),
            "discount_amount": float(order.discount_amount),
            "tax_amount": float(order.tax_amount),
            "paid_amount": float(order.paid_amount),
            "currency": order.currency,
            "order_note": order.order_note,
            "shipping_address": shipping_address,
            "created_at": order.created_at.isoformat(),
            "items": [
                {
                    "product_id": str(item.product_id),
                    "product_name": item.product_name,
                    "quantity": item.quantity,
                    "unit_price": float(item.unit_price),
                }
                for item in items
            ],
        }

    @staticmethod
    async def update_status(db: AsyncSession, order_id: UUID, new_status: str) -> dict:
        order = (
            await db.execute(
                select(EcommerceOrder).where(
                    EcommerceOrder.id == order_id,
                    EcommerceOrder.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if not order:
            raise AppError(404, "Order not found", "order_not_found")
        try:
            status = EcommerceOrderStatus(new_status)
        except ValueError as exc:
            raise AppError(400, "Invalid order status", "invalid_status") from exc
        order.order_status = status
        await db.flush()
        if order.customer_id:
            from app.models.ecommerce.accounts import CustomerAccount
            from app.services.ecommerce.notification_service import EcommerceNotificationService

            customer = await db.get(CustomerAccount, order.customer_id)
            if customer:
                await EcommerceNotificationService.notify_customer(
                    db,
                    customer_id=customer.id,
                    title=f"Order {order.public_id} updated",
                    body=f"Your order status is now: {status.value.replace('_', ' ')}",
                    notification_type="order_status",
                    reference_id=order.id,
                    email=customer.email,
                )
        return {"message": "Order status updated", "order_status": status.value}
