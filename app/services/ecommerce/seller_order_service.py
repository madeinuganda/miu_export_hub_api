from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.shared.exceptions import AppError
from app.models.ecommerce.accounts import EcommerceShop, SellerAccount
from app.models.ecommerce.orders import EcommerceOrder, EcommerceOrderItem
from app.models.shared.enums import EcommerceOrderStatus


class EcommerceSellerOrderService:
    @staticmethod
    async def _shop_for_seller(db: AsyncSession, seller: SellerAccount) -> EcommerceShop:
        shop = (
            await db.execute(
                select(EcommerceShop).where(
                    EcommerceShop.seller_account_id == seller.id,
                    EcommerceShop.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if not shop:
            raise AppError(404, "Shop not found for seller", "shop_not_found")
        return shop

    @staticmethod
    async def list_orders(
        db: AsyncSession,
        seller: SellerAccount,
        status: str = "all",
        limit: int = 10,
        offset: int = 1,
    ) -> dict:
        shop = await EcommerceSellerOrderService._shop_for_seller(db, seller)
        query = select(EcommerceOrder).where(
            EcommerceOrder.shop_id == shop.id,
            EcommerceOrder.deleted_at.is_(None),
        )
        count_base = (
            EcommerceOrder.shop_id == shop.id,
            EcommerceOrder.deleted_at.is_(None),
        )
        if status != "all":
            try:
                status_enum = EcommerceOrderStatus(status)
            except ValueError as exc:
                raise AppError(400, "Invalid order status filter", "invalid_status") from exc
            query = query.where(EcommerceOrder.order_status == status_enum)
            count_filters = (*count_base, EcommerceOrder.order_status == status_enum)
        else:
            count_filters = count_base

        total = (
            await db.execute(select(func.count()).select_from(EcommerceOrder).where(*count_filters))
        ).scalar_one()

        page = max(offset, 1)
        skip = (page - 1) * limit
        orders = (
            await db.execute(
                query.order_by(EcommerceOrder.created_at.desc()).offset(skip).limit(limit)
            )
        ).scalars().all()

        serialized = []
        for order in orders:
            items = (
                await db.execute(
                    select(EcommerceOrderItem).where(
                        EcommerceOrderItem.order_id == order.id,
                        EcommerceOrderItem.deleted_at.is_(None),
                    )
                )
            ).scalars().all()
            serialized.append(
                {
                    "id": str(order.id),
                    "order_id": order.public_id,
                    "order_status": order.order_status.value,
                    "payment_status": order.payment_status.value,
                    "payment_method": order.payment_method.value,
                    "order_amount": float(order.order_amount),
                    "shipping_cost": float(order.shipping_cost),
                    "created_at": order.created_at.isoformat(),
                    "items_count": len(items),
                }
            )

        return {
            "total_size": total,
            "limit": limit,
            "offset": page,
            "orders": serialized,
        }

    @staticmethod
    async def order_details(
        db: AsyncSession,
        seller: SellerAccount,
        order_id: UUID,
    ) -> dict:
        shop = await EcommerceSellerOrderService._shop_for_seller(db, seller)
        order = (
            await db.execute(
                select(EcommerceOrder).where(
                    EcommerceOrder.id == order_id,
                    EcommerceOrder.shop_id == shop.id,
                    EcommerceOrder.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if not order:
            raise AppError(404, "Order not found", "order_not_found")

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
            "order_status": order.order_status.value,
            "payment_status": order.payment_status.value,
            "payment_method": order.payment_method.value,
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
                    "product_slug": item.product_slug,
                    "quantity": item.quantity,
                    "unit_price": float(item.unit_price),
                    "discount": float(item.discount),
                    "discount_type": item.discount_type.value,
                }
                for item in items
            ],
        }

    @staticmethod
    async def update_order_status(
        db: AsyncSession,
        seller: SellerAccount,
        order_id: UUID,
        new_status: str,
    ) -> dict:
        shop = await EcommerceSellerOrderService._shop_for_seller(db, seller)
        order = (
            await db.execute(
                select(EcommerceOrder).where(
                    EcommerceOrder.id == order_id,
                    EcommerceOrder.shop_id == shop.id,
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

        allowed = {
            EcommerceOrderStatus.CONFIRMED,
            EcommerceOrderStatus.PROCESSING,
            EcommerceOrderStatus.OUT_FOR_DELIVERY,
            EcommerceOrderStatus.DELIVERED,
        }
        if status not in allowed:
            raise AppError(400, "Status transition not allowed", "invalid_status")

        order.order_status = status
        await db.flush()
        return {"message": "Order status updated", "order_status": status.value}
