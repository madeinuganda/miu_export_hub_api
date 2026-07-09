from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ecommerce.deps import CartOwnerContext
from app.core.shared.config import get_settings
from app.core.shared.exceptions import AppError
from app.models.ecommerce.orders import EcommerceCartShipping


class EcommerceShippingService:
    @staticmethod
    def _default_methods() -> list[dict]:
        settings = get_settings()
        cost = Decimal(str(settings.ecommerce_default_shipping_cost))
        return [
            {
                "id": "flat_standard",
                "title": "Standard Delivery",
                "duration": "2-5 business days",
                "cost": float(cost),
                "currency": "UGX",
            }
        ]

    @staticmethod
    def _owner_filter(owner: CartOwnerContext):
        return (
            EcommerceCartShipping.owner_id == owner.owner_id,
            EcommerceCartShipping.is_guest == owner.is_guest,
            EcommerceCartShipping.deleted_at.is_(None),
        )

    @staticmethod
    async def methods_for_shop(db: AsyncSession, shop_id: UUID) -> list[dict]:
        from app.models.ecommerce.shipping_config import EcommerceShopShippingMethod

        rows = (
            await db.execute(
                select(EcommerceShopShippingMethod)
                .where(
                    EcommerceShopShippingMethod.shop_id == shop_id,
                    EcommerceShopShippingMethod.is_active.is_(True),
                    EcommerceShopShippingMethod.deleted_at.is_(None),
                )
                .order_by(EcommerceShopShippingMethod.sort_order)
            )
        ).scalars().all()
        if rows:
            return [
                {
                    "id": row.code,
                    "title": row.title,
                    "duration": row.duration,
                    "cost": float(row.cost),
                    "currency": row.currency,
                }
                for row in rows
            ]
        return EcommerceShippingService._default_methods()

    @staticmethod
    async def _methods_for_shop(db: AsyncSession, shop_id: UUID) -> list[dict]:
        return await EcommerceShippingService.methods_for_shop(db, shop_id)

    @staticmethod
    async def check_shipping_type(db: AsyncSession, shop_id: UUID) -> dict:
        _ = db
        return {"shop_id": str(shop_id), "shipping_type": "order_wise"}

    @staticmethod
    async def choose_for_order(
        db: AsyncSession,
        owner: CartOwnerContext,
        cart_group_id: UUID,
        method_id: str,
    ) -> dict:
        methods = {m["id"]: m for m in await EcommerceShippingService._methods_for_shop(db, cart_group_id)}
        if not methods:
            methods = {m["id"]: m for m in EcommerceShippingService._default_methods()}
        method = methods.get(method_id)
        if not method:
            raise AppError(404, "Shipping method not found", "shipping_method_not_found")

        owner_filter = EcommerceShippingService._owner_filter(owner)
        existing = (
            await db.execute(
                select(EcommerceCartShipping).where(
                    *owner_filter,
                    EcommerceCartShipping.cart_group_id == cart_group_id,
                )
            )
        ).scalar_one_or_none()

        if existing:
            existing.shipping_method_code = method_id
            existing.shipping_method_title = method["title"]
            existing.shipping_cost = Decimal(str(method["cost"]))
        else:
            db.add(
                EcommerceCartShipping(
                    owner_id=owner.owner_id,
                    is_guest=owner.is_guest,
                    cart_group_id=cart_group_id,
                    shipping_method_code=method_id,
                    shipping_method_title=method["title"],
                    shipping_cost=Decimal(str(method["cost"])),
                )
            )
        await db.flush()
        return {"status": 1, "message": "Shipping method selected"}

    @staticmethod
    async def chosen_methods(db: AsyncSession, owner: CartOwnerContext) -> list[dict]:
        owner_filter = EcommerceShippingService._owner_filter(owner)
        rows = (
            await db.execute(
                select(EcommerceCartShipping).where(*owner_filter)
            )
        ).scalars().all()
        return [
            {
                "cart_group_id": str(row.cart_group_id),
                "id": row.shipping_method_code,
                "title": row.shipping_method_title,
                "cost": float(row.shipping_cost),
            }
            for row in rows
        ]

    @staticmethod
    async def shipping_map(db: AsyncSession, owner: CartOwnerContext) -> dict[UUID, EcommerceCartShipping]:
        owner_filter = EcommerceShippingService._owner_filter(owner)
        rows = (
            await db.execute(
                select(EcommerceCartShipping).where(*owner_filter)
            )
        ).scalars().all()
        return {row.cart_group_id: row for row in rows}

    @staticmethod
    async def require_shipping_for_groups(
        db: AsyncSession,
        owner: CartOwnerContext,
        cart_group_ids: set[UUID],
    ) -> dict[UUID, EcommerceCartShipping]:
        shipping = await EcommerceShippingService.shipping_map(db, owner)
        missing = cart_group_ids - set(shipping.keys())
        if missing:
            raise AppError(
                400,
                "Select shipping method for all shops before checkout",
                "shipping_required",
            )
        return shipping

    @staticmethod
    async def clear_for_owner(db: AsyncSession, owner: CartOwnerContext) -> None:
        owner_filter = EcommerceShippingService._owner_filter(owner)
        await db.execute(delete(EcommerceCartShipping).where(*owner_filter))
