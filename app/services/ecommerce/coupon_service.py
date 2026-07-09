from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ecommerce.deps import CartOwnerContext
from app.core.shared.exceptions import AppError
from app.models.ecommerce.cart import EcommerceCartItem
from app.models.ecommerce.orders import EcommerceOrder
from app.models.ecommerce.promotions import EcommerceCoupon, EcommerceCouponUsage
from app.models.shared.enums import EcommerceCouponType, EcommerceDiscountType
from app.services.ecommerce.cart_service import EcommerceCartService
from app.services.ecommerce.shipping_service import EcommerceShippingService


class EcommerceCouponService:
    @staticmethod
    def _today() -> date:
        return date.today()

    @staticmethod
    async def _checked_cart(db: AsyncSession, owner: CartOwnerContext) -> list[EcommerceCartItem]:
        owner_filter = EcommerceCartService._owner_filter(owner)
        items = (
            await db.execute(
                select(EcommerceCartItem).where(
                    *owner_filter,
                    EcommerceCartItem.is_checked.is_(True),
                )
            )
        ).scalars().all()
        if not items:
            raise AppError(400, "No checked items in cart", "empty_cart")
        return items

    @staticmethod
    def _subtotal_for_items(items: list[EcommerceCartItem]) -> Decimal:
        total = Decimal("0")
        for item in items:
            total += EcommerceCartService._line_sale_price(item) * item.quantity
        return total

    @staticmethod
    async def _get_coupon(db: AsyncSession, code: str) -> EcommerceCoupon:
        coupon = (
            await db.execute(
                select(EcommerceCoupon).where(
                    EcommerceCoupon.code == code.upper(),
                    EcommerceCoupon.deleted_at.is_(None),
                    EcommerceCoupon.is_active.is_(True),
                )
            )
        ).scalar_one_or_none()
        if not coupon:
            raise AppError(202, "invalid_coupon", "invalid_coupon")
        today = EcommerceCouponService._today()
        if coupon.start_date > today or coupon.expire_date < today:
            raise AppError(202, "invalid_coupon", "invalid_coupon")
        return coupon

    @staticmethod
    async def _usage_counts(
        db: AsyncSession, coupon_id: UUID, customer_id: UUID
    ) -> tuple[int, int]:
        customer_usage = (
            await db.execute(
                select(func.count())
                .select_from(EcommerceCouponUsage)
                .where(
                    EcommerceCouponUsage.coupon_id == coupon_id,
                    EcommerceCouponUsage.customer_id == customer_id,
                    EcommerceCouponUsage.deleted_at.is_(None),
                )
            )
        ).scalar_one()
        total_usage = (
            await db.execute(
                select(func.count())
                .select_from(EcommerceCouponUsage)
                .where(
                    EcommerceCouponUsage.coupon_id == coupon_id,
                    EcommerceCouponUsage.deleted_at.is_(None),
                )
            )
        ).scalar_one()
        return customer_usage, total_usage

    @staticmethod
    async def _eligible_items(
        db: AsyncSession,
        owner: CartOwnerContext,
        coupon: EcommerceCoupon,
        items: list[EcommerceCartItem],
    ) -> list[EcommerceCartItem]:
        if coupon.shop_id:
            return [item for item in items if item.shop_id == coupon.shop_id]
        return items

    @staticmethod
    async def calculate_discount(
        db: AsyncSession,
        owner: CartOwnerContext,
        code: str,
        shipping_map: dict | None = None,
    ) -> tuple[EcommerceCoupon, Decimal, dict[UUID, Decimal]]:
        if owner.is_guest:
            raise AppError(401, "Login required to apply coupons", "unauthorized")

        coupon = await EcommerceCouponService._get_coupon(db, code)
        items = await EcommerceCouponService._checked_cart(db, owner)
        eligible = await EcommerceCouponService._eligible_items(db, owner, coupon, items)

        if coupon.customer_id and coupon.customer_id != owner.owner_id:
            raise AppError(202, "invalid_coupon", "invalid_coupon")

        customer_usage, total_usage = await EcommerceCouponService._usage_counts(
            db, coupon.id, owner.owner_id
        )
        if coupon.usage_limit is not None and customer_usage >= coupon.usage_limit:
            raise AppError(202, "invalid_coupon", "invalid_coupon")
        if coupon.total_limit is not None and total_usage >= coupon.total_limit:
            raise AppError(202, "invalid_coupon", "invalid_coupon")

        if coupon.coupon_type == EcommerceCouponType.FIRST_ORDER:
            prior = (
                await db.execute(
                    select(func.count())
                    .select_from(EcommerceOrder)
                    .where(
                        EcommerceOrder.customer_id == owner.owner_id,
                        EcommerceOrder.deleted_at.is_(None),
                    )
                )
            ).scalar_one()
            if prior > 0:
                raise AppError(202, "invalid_coupon", "invalid_coupon")

        subtotal = EcommerceCouponService._subtotal_for_items(eligible)
        if subtotal <= 0 or subtotal < coupon.min_purchase:
            raise AppError(202, "invalid_coupon", "invalid_coupon")

        if coupon.coupon_type == EcommerceCouponType.FREE_DELIVERY:
            if not shipping_map:
                shipping_map = await EcommerceShippingService.shipping_map(db, owner)
            discount = Decimal("0")
            shop_groups: dict[UUID, Decimal] = {}
            for item in eligible:
                ship = shipping_map.get(item.cart_group_id) or shipping_map.get(item.shop_id)
                if ship and item.shop_id not in shop_groups:
                    shop_groups[item.shop_id] = ship.shipping_cost
            discount = sum(shop_groups.values(), Decimal("0"))
            split = shop_groups
            return coupon, discount, split

        if coupon.discount_type == EcommerceDiscountType.PERCENT:
            discount = (subtotal * coupon.discount / Decimal("100")).quantize(Decimal("0.01"))
            if coupon.max_discount is not None:
                discount = min(discount, coupon.max_discount)
        else:
            discount = min(coupon.discount, subtotal)

        grouped: dict[UUID, Decimal] = {}
        for item in eligible:
            grouped[item.shop_id] = grouped.get(item.shop_id, Decimal("0")) + (
                EcommerceCartService._line_sale_price(item) * item.quantity
            )
        split: dict[UUID, Decimal] = {}
        for shop_id, shop_sub in grouped.items():
            if subtotal > 0:
                split[shop_id] = (discount * shop_sub / subtotal).quantize(Decimal("0.01"))

        return coupon, discount, split

    @staticmethod
    async def apply(db: AsyncSession, owner: CartOwnerContext, code: str) -> dict:
        coupon, discount, _ = await EcommerceCouponService.calculate_discount(db, owner, code)
        return {
            "coupon_discount": float(discount),
            "coupon_type": coupon.coupon_type.value,
            "code": coupon.code,
        }

    @staticmethod
    async def list_coupons(
        db: AsyncSession,
        owner: CartOwnerContext,
        limit: int = 10,
        offset: int = 1,
    ) -> dict:
        if owner.is_guest:
            raise AppError(401, "Login required", "unauthorized")
        today = EcommerceCouponService._today()
        query = select(EcommerceCoupon).where(
            EcommerceCoupon.deleted_at.is_(None),
            EcommerceCoupon.is_active.is_(True),
            EcommerceCoupon.start_date <= today,
            EcommerceCoupon.expire_date >= today,
        )
        total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar_one()
        page = max(offset, 1)
        skip = (page - 1) * limit
        coupons = (
            await db.execute(query.order_by(EcommerceCoupon.created_at.desc()).offset(skip).limit(limit))
        ).scalars().all()
        return {
            "total_size": total,
            "limit": limit,
            "offset": page,
            "coupons": [
                {
                    "id": str(c.id),
                    "title": c.title,
                    "code": c.code,
                    "coupon_type": c.coupon_type.value,
                    "discount": float(c.discount),
                    "discount_type": c.discount_type.value,
                    "min_purchase": float(c.min_purchase),
                    "expire_date": c.expire_date.isoformat(),
                }
                for c in coupons
            ],
        }

    @staticmethod
    async def applicable_list(db: AsyncSession, owner: CartOwnerContext) -> list[dict]:
        if owner.is_guest:
            raise AppError(401, "Login required", "unauthorized")
        today = EcommerceCouponService._today()
        coupons = (
            await db.execute(
                select(EcommerceCoupon).where(
                    EcommerceCoupon.deleted_at.is_(None),
                    EcommerceCoupon.is_active.is_(True),
                    EcommerceCoupon.start_date <= today,
                    EcommerceCoupon.expire_date >= today,
                )
            )
        ).scalars().all()
        applicable = []
        for coupon in coupons:
            try:
                _, discount, _ = await EcommerceCouponService.calculate_discount(
                    db, owner, coupon.code
                )
                applicable.append(
                    {
                        "id": str(coupon.id),
                        "title": coupon.title,
                        "code": coupon.code,
                        "coupon_type": coupon.coupon_type.value,
                        "coupon_discount": float(discount),
                    }
                )
            except AppError:
                continue
        return applicable

    @staticmethod
    async def record_usage(
        db: AsyncSession,
        coupon_id: UUID,
        customer_id: UUID,
        order_group_id: UUID,
    ) -> None:
        db.add(
            EcommerceCouponUsage(
                coupon_id=coupon_id,
                customer_id=customer_id,
                order_group_id=order_group_id,
            )
        )
