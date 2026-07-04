from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ecommerce.deps import CartOwnerContext
from app.core.shared.exceptions import AppError
from app.models.ecommerce.accounts import EcommerceShop
from app.models.ecommerce.cart import EcommerceCartItem
from app.models.ecommerce.catalog import EcommerceProduct
from app.models.shared.enums import EcommerceProductStatus, StockStatus
from app.services.ecommerce.catalog_service import EcommerceCatalogService


class EcommerceCartService:
    @staticmethod
    def _line_sale_price(item: EcommerceCartItem) -> Decimal:
        product_like = type(
            "P",
            (),
            {
                "unit_price": item.unit_price,
                "discount": item.discount,
                "discount_type": item.discount_type,
            },
        )()
        return EcommerceCatalogService._sale_price(product_like)  # type: ignore[arg-type]

    @staticmethod
    def _discount_per_unit(item: EcommerceCartItem) -> Decimal:
        return max(item.unit_price - EcommerceCartService._line_sale_price(item), Decimal("0"))

    @staticmethod
    async def _get_product(db: AsyncSession, product_id: UUID) -> EcommerceProduct:
        product = (
            await db.execute(
                select(EcommerceProduct).where(
                    EcommerceProduct.id == product_id,
                    EcommerceProduct.deleted_at.is_(None),
                    EcommerceProduct.status == EcommerceProductStatus.PUBLISHED,
                )
            )
        ).scalar_one_or_none()
        if not product:
            raise AppError(404, "Product not found", "product_not_found")
        return product

    @staticmethod
    def _owner_filter(owner: CartOwnerContext):
        return (
            EcommerceCartItem.owner_id == owner.owner_id,
            EcommerceCartItem.is_guest == owner.is_guest,
            EcommerceCartItem.deleted_at.is_(None),
        )

    @staticmethod
    async def _serialize_item(db: AsyncSession, item: EcommerceCartItem) -> dict:
        product = (
            await db.execute(
                select(EcommerceProduct).where(
                    EcommerceProduct.id == item.product_id,
                    EcommerceProduct.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        shop = (
            await db.execute(
                select(EcommerceShop).where(
                    EcommerceShop.id == item.shop_id,
                    EcommerceShop.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        sale = EcommerceCartService._line_sale_price(item)
        discount_amt = EcommerceCartService._discount_per_unit(item)
        is_available = bool(
            product
            and product.status == EcommerceProductStatus.PUBLISHED
            and product.current_stock >= item.quantity
            and product.stock_status != StockStatus.OUT_OF_STOCK
        )
        product_payload = None
        if product:
            product_payload = await EcommerceCatalogService._product_card(db, product)
        return {
            "id": str(item.id),
            "product_id": str(item.product_id),
            "shop_id": str(item.shop_id),
            "cart_group_id": str(item.cart_group_id),
            "quantity": item.quantity,
            "price": float(item.unit_price),
            "discount": float(discount_amt),
            "discount_type": item.discount_type.value,
            "sale_price": float(sale),
            "is_checked": item.is_checked,
            "is_guest": item.is_guest,
            "is_product_available": 1 if is_available else 0,
            "product_name": item.product_name,
            "product_slug": item.product_slug,
            "product_thumbnail": item.product_thumbnail,
            "shop": {"id": str(shop.id), "name": shop.name, "slug": shop.slug} if shop else None,
            "product": product_payload,
        }

    @staticmethod
    async def list_cart(db: AsyncSession, owner: CartOwnerContext) -> list[dict]:
        owner_filter = EcommerceCartService._owner_filter(owner)
        items = (
            await db.execute(
                select(EcommerceCartItem)
                .where(*owner_filter)
                .order_by(EcommerceCartItem.created_at)
            )
        ).scalars().all()

        result: list[dict] = []
        for item in items:
            product = (
                await db.execute(
                    select(EcommerceProduct).where(
                        EcommerceProduct.id == item.product_id,
                        EcommerceProduct.deleted_at.is_(None),
                        EcommerceProduct.status == EcommerceProductStatus.PUBLISHED,
                    )
                )
            ).scalar_one_or_none()
            if not product:
                await db.execute(
                    delete(EcommerceCartItem).where(EcommerceCartItem.id == item.id)
                )
                continue
            result.append(await EcommerceCartService._serialize_item(db, item))
        return result

    @staticmethod
    async def add_to_cart(
        db: AsyncSession,
        owner: CartOwnerContext,
        product_id: UUID,
        quantity: int,
    ) -> dict:
        product = await EcommerceCartService._get_product(db, product_id)
        if product.current_stock < quantity or product.stock_status == StockStatus.OUT_OF_STOCK:
            return {"status": 0, "message": "out_of_stock!"}
        if quantity < product.minimum_order_qty:
            return {
                "status": 0,
                "message": f"Minimum order quantity {product.minimum_order_qty}",
            }

        shop = (
            await db.execute(
                select(EcommerceShop).where(
                    EcommerceShop.id == product.shop_id,
                    EcommerceShop.deleted_at.is_(None),
                    EcommerceShop.is_published.is_(True),
                )
            )
        ).scalar_one_or_none()
        if not shop:
            return {"status": 0, "message": "Shop is not available"}

        owner_filter = EcommerceCartService._owner_filter(owner)
        existing = (
            await db.execute(
                select(EcommerceCartItem).where(
                    *owner_filter,
                    EcommerceCartItem.product_id == product_id,
                )
            )
        ).scalar_one_or_none()

        if existing:
            new_qty = existing.quantity + quantity
            if product.current_stock < new_qty:
                return {"status": 0, "message": "out_of_stock!"}
            existing.quantity = new_qty
            existing.unit_price = product.unit_price
            existing.discount = product.discount
            existing.discount_type = product.discount_type
            existing.product_name = product.name
            existing.product_slug = product.slug
            existing.product_thumbnail = product.thumbnail_url
            await db.flush()
            return {"status": 1, "message": "added_to_cart_successfully!", "cart_id": str(existing.id)}

        item = EcommerceCartItem(
            owner_id=owner.owner_id,
            is_guest=owner.is_guest,
            cart_group_id=product.shop_id,
            shop_id=product.shop_id,
            product_id=product.id,
            quantity=quantity,
            unit_price=product.unit_price,
            discount=product.discount,
            discount_type=product.discount_type,
            product_name=product.name,
            product_slug=product.slug,
            product_thumbnail=product.thumbnail_url,
        )
        db.add(item)
        await db.flush()
        return {"status": 1, "message": "added_to_cart_successfully!", "cart_id": str(item.id)}

    @staticmethod
    async def update_quantity(
        db: AsyncSession,
        owner: CartOwnerContext,
        item_id: UUID,
        quantity: int,
    ) -> dict:
        owner_filter = EcommerceCartService._owner_filter(owner)
        item = (
            await db.execute(
                select(EcommerceCartItem).where(
                    *owner_filter,
                    EcommerceCartItem.id == item_id,
                )
            )
        ).scalar_one_or_none()
        if not item:
            return {"status": 0, "qty": quantity, "message": "Product_not_found_in_cart"}

        product = await EcommerceCartService._get_product(db, item.product_id)
        if product.current_stock < quantity:
            return {
                "status": 0,
                "qty": item.quantity,
                "message": "sorry_stock_is_limited",
            }

        item.quantity = quantity
        await db.flush()
        return {"status": 1, "qty": quantity, "message": "successfully_updated!"}

    @staticmethod
    async def remove_item(db: AsyncSession, owner: CartOwnerContext, item_id: UUID) -> str:
        owner_filter = EcommerceCartService._owner_filter(owner)
        result = await db.execute(
            delete(EcommerceCartItem).where(
                *owner_filter,
                EcommerceCartItem.id == item_id,
            )
        )
        if result.rowcount == 0:
            raise AppError(404, "Cart item not found", "cart_item_not_found")
        return "successfully_removed"

    @staticmethod
    async def remove_all(db: AsyncSession, owner: CartOwnerContext) -> str:
        owner_filter = EcommerceCartService._owner_filter(owner)
        await db.execute(delete(EcommerceCartItem).where(*owner_filter))
        return "successfully_removed"

    @staticmethod
    async def select_items(
        db: AsyncSession,
        owner: CartOwnerContext,
        item_ids: list[UUID],
        action: str,
    ) -> str:
        checked = action == "checked"
        owner_filter = EcommerceCartService._owner_filter(owner)
        await db.execute(
            update(EcommerceCartItem)
            .where(
                *owner_filter,
                EcommerceCartItem.id.in_(item_ids),
            )
            .values(is_checked=checked)
        )
        return "Successfully_Update"

    @staticmethod
    async def summary(db: AsyncSession, owner: CartOwnerContext, checked_only: bool = True) -> dict:
        owner_filter = EcommerceCartService._owner_filter(owner)
        query = select(EcommerceCartItem).where(*owner_filter)
        if checked_only:
            query = query.where(EcommerceCartItem.is_checked.is_(True))
        items = (await db.execute(query)).scalars().all()

        subtotal = Decimal("0")
        discount_total = Decimal("0")
        for item in items:
            sale = EcommerceCartService._line_sale_price(item)
            subtotal += sale * item.quantity
            discount_total += EcommerceCartService._discount_per_unit(item) * item.quantity

        shipping_cost = Decimal("0")
        tax = Decimal("0")
        total = subtotal + shipping_cost + tax

        return {
            "item_count": len(items),
            "checked_item_count": len(items) if checked_only else sum(1 for i in items if i.is_checked),
            "subtotal": float(subtotal),
            "discount_total": float(discount_total),
            "shipping_cost": float(shipping_cost),
            "tax": float(tax),
            "total": float(total),
            "currency": "UGX",
        }

    @staticmethod
    async def checkout_preview(db: AsyncSession, owner: CartOwnerContext) -> dict:
        from app.core.shared.config import get_settings
        from app.services.ecommerce.shipping_service import EcommerceShippingService

        settings = get_settings()
        cart = await EcommerceCartService.list_cart(db, owner)
        checked = [row for row in cart if row.get("is_checked")]
        summary = await EcommerceCartService.summary(db, owner, checked_only=True)
        chosen_shipping = await EcommerceShippingService.chosen_methods(db, owner)
        shipping_total = sum(row["cost"] for row in chosen_shipping)
        tax_rate = settings.ecommerce_tax_rate_percent
        subtotal = Decimal(str(summary["subtotal"]))
        tax = (subtotal * Decimal(str(tax_rate)) / Decimal("100")).quantize(Decimal("0.01"))
        total = subtotal + Decimal(str(shipping_total)) + tax

        return {
            "cart": checked,
            "summary": {
                **summary,
                "shipping_cost": float(shipping_total),
                "tax": float(tax),
                "total": float(total),
            },
            "shipping_methods": EcommerceShippingService._default_methods(),
            "chosen_shipping": chosen_shipping,
            "payment_methods": [
                {"code": "cash_on_delivery", "name": "Cash on Delivery", "enabled": True},
                {
                    "code": "pesapal",
                    "name": "Pesapal",
                    "enabled": settings.pesapal_enabled,
                },
            ],
        }

    @staticmethod
    async def merge_guest_cart(
        db: AsyncSession,
        guest_id: UUID,
        customer_id: UUID,
    ) -> int:
        """Move guest cart lines to the customer account (Laravel CartManager::cartListSessionToDatabase)."""
        from app.models.ecommerce.catalog import EcommerceGuest

        guest = (
            await db.execute(
                select(EcommerceGuest).where(
                    EcommerceGuest.id == guest_id,
                    EcommerceGuest.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if not guest:
            return 0

        guest_items = (
            await db.execute(
                select(EcommerceCartItem).where(
                    EcommerceCartItem.owner_id == guest_id,
                    EcommerceCartItem.is_guest.is_(True),
                    EcommerceCartItem.deleted_at.is_(None),
                )
            )
        ).scalars().all()
        if not guest_items:
            return 0

        customer_owner = CartOwnerContext(owner_id=customer_id, is_guest=False)
        merged = 0
        for guest_item in guest_items:
            customer_shop_item = (
                await db.execute(
                    select(EcommerceCartItem).where(
                        *EcommerceCartService._owner_filter(customer_owner),
                        EcommerceCartItem.shop_id == guest_item.shop_id,
                    )
                    .limit(1)
                )
            ).scalar_one_or_none()

            await db.execute(
                delete(EcommerceCartItem).where(
                    *EcommerceCartService._owner_filter(customer_owner),
                    EcommerceCartItem.product_id == guest_item.product_id,
                )
            )

            guest_item.owner_id = customer_id
            guest_item.is_guest = False
            if customer_shop_item:
                guest_item.cart_group_id = customer_shop_item.cart_group_id
            merged += 1

        await db.flush()
        return merged
