from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ecommerce.deps import CartOwnerContext
from app.core.shared.config import get_settings
from app.core.shared.exceptions import AppError
from app.models.ecommerce.accounts import CustomerAccount
from app.models.ecommerce.cart import EcommerceCartItem
from app.models.ecommerce.catalog import EcommerceProduct
from app.models.ecommerce.promotions import EcommerceCoupon
from app.models.ecommerce.orders import EcommerceOrder, EcommerceOrderItem, EcommercePaymentRequest
from app.models.shared.enums import (
    EcommerceOrderStatus,
    EcommercePaymentMethod,
    EcommercePaymentStatus,
    EcommerceProductStatus,
    StockStatus,
)
from app.services.ecommerce.cart_service import EcommerceCartService
from app.services.ecommerce.address_service import EcommerceAddressService
from app.services.ecommerce.coupon_service import EcommerceCouponService
from app.services.ecommerce.shipping_service import EcommerceShippingService
from app.services.ecommerce.wallet_service import EcommerceWalletService


class EcommerceOrderService:
    @staticmethod
    async def _next_public_id(db: AsyncSession) -> str:
        year = datetime.now(timezone.utc).year
        count = (
            await db.execute(
                select(func.count()).select_from(EcommerceOrder).where(
                    EcommerceOrder.public_id.like(f"MIU-SHP-{year}-%")
                )
            )
        ).scalar_one()
        return f"MIU-SHP-{year}-{count + 1:05d}"

    @staticmethod
    async def _load_checked_cart(db: AsyncSession, owner: CartOwnerContext) -> list[EcommerceCartItem]:
        owner_filter = EcommerceCartService._owner_filter(owner)
        items = (
            await db.execute(
                select(EcommerceCartItem)
                .where(*owner_filter, EcommerceCartItem.is_checked.is_(True))
                .order_by(EcommerceCartItem.created_at)
            )
        ).scalars().all()
        if not items:
            raise AppError(400, "No checked items in cart", "empty_cart")
        return items

    @staticmethod
    async def _validate_cart_stock(db: AsyncSession, items: list[EcommerceCartItem]) -> None:
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
            if not product or product.current_stock < item.quantity:
                raise AppError(
                    403,
                    "The following items in your cart are currently out of stock",
                    "out_of_stock",
                )
            if product.stock_status == StockStatus.OUT_OF_STOCK:
                raise AppError(403, "Product out of stock", "out_of_stock")

    @staticmethod
    async def _resolve_address_snapshot(
        db: AsyncSession,
        owner: CartOwnerContext,
        address_id: UUID | None,
    ) -> tuple[UUID | None, str | None]:
        if not address_id:
            return None, None
        row = await EcommerceAddressService.get_address_for_checkout(db, owner, address_id)
        return row.id, EcommerceAddressService.address_snapshot(row)

    @staticmethod
    async def _totals_for_group(
        items: list[EcommerceCartItem],
        shipping_cost: Decimal,
        coupon_discount: Decimal = Decimal("0"),
    ) -> tuple[Decimal, Decimal, Decimal, Decimal]:
        settings = get_settings()
        subtotal = Decimal("0")
        discount_total = Decimal("0")
        for item in items:
            sale = EcommerceCartService._line_sale_price(item)
            subtotal += sale * item.quantity
            discount_total += EcommerceCartService._discount_per_unit(item) * item.quantity
        tax = (subtotal * Decimal(str(settings.ecommerce_tax_rate_percent)) / Decimal("100")).quantize(
            Decimal("0.01")
        )
        order_amount = max(subtotal + shipping_cost + tax - coupon_discount, Decimal("0"))
        return order_amount, discount_total, tax, subtotal

    @staticmethod
    async def _resolve_coupon(
        db: AsyncSession,
        owner: CartOwnerContext,
        coupon_code: str | None,
        shipping_map: dict,
    ) -> tuple[EcommerceCoupon | None, dict[UUID, Decimal]]:
        if not coupon_code or owner.is_guest:
            return None, {}
        coupon, _, split = await EcommerceCouponService.calculate_discount(
            db, owner, coupon_code, shipping_map=shipping_map
        )
        return coupon, split

    @staticmethod
    async def generate_orders_from_cart(
        db: AsyncSession,
        owner: CartOwnerContext,
        *,
        payment_method: EcommercePaymentMethod,
        order_status: EcommerceOrderStatus,
        payment_status: EcommercePaymentStatus,
        transaction_ref: str | None = None,
        address_id: UUID | None = None,
        order_note: str | None = None,
        paid_amount: Decimal | None = None,
        coupon_code: str | None = None,
    ) -> list[UUID]:
        items = await EcommerceOrderService._load_checked_cart(db, owner)
        await EcommerceOrderService._validate_cart_stock(db, items)

        cart_groups = {item.cart_group_id for item in items}
        shipping_map = await EcommerceShippingService.require_shipping_for_groups(
            db, owner, cart_groups
        )

        customer_id = None if owner.is_guest else owner.owner_id
        guest_id = owner.owner_id if owner.is_guest else None
        resolved_address_id, address_snapshot = await EcommerceOrderService._resolve_address_snapshot(
            db, owner, address_id
        )

        grouped: dict[UUID, list[EcommerceCartItem]] = defaultdict(list)
        for item in items:
            grouped[item.shop_id].append(item)

        coupon, coupon_split = await EcommerceOrderService._resolve_coupon(
            db, owner, coupon_code, shipping_map
        )
        is_free_delivery = coupon and coupon.coupon_type.value == "free_delivery"

        order_group_id = uuid4()
        created_order_ids: list[UUID] = []

        for shop_id, shop_items in grouped.items():
            shipping = shipping_map.get(shop_id) or shipping_map.get(shop_items[0].cart_group_id)
            if not shipping:
                raise AppError(400, "Shipping not selected for shop", "shipping_required")
            shipping_cost = Decimal("0") if is_free_delivery else shipping.shipping_cost
            shop_coupon_discount = coupon_split.get(shop_id, Decimal("0"))
            order_amount, discount_total, tax, _ = await EcommerceOrderService._totals_for_group(
                shop_items, shipping_cost, coupon_discount=shop_coupon_discount
            )
            paid = paid_amount if paid_amount is not None else (
                order_amount if payment_status == EcommercePaymentStatus.PAID else Decimal("0")
            )

            order = EcommerceOrder(
                public_id=await EcommerceOrderService._next_public_id(db),
                order_group_id=order_group_id,
                customer_id=customer_id,
                guest_id=guest_id,
                is_guest=owner.is_guest,
                shop_id=shop_id,
                order_status=order_status,
                payment_status=payment_status,
                payment_method=payment_method,
                transaction_ref=transaction_ref,
                order_amount=order_amount,
                shipping_cost=shipping_cost,
                discount_amount=discount_total,
                tax_amount=tax,
                paid_amount=paid,
                shipping_address_id=resolved_address_id,
                shipping_address_snapshot=address_snapshot,
                order_note=order_note,
                coupon_code=coupon.code if coupon else None,
                coupon_discount=shop_coupon_discount,
            )
            db.add(order)
            await db.flush()

            for cart_item in shop_items:
                product = (
                    await db.execute(
                        select(EcommerceProduct).where(EcommerceProduct.id == cart_item.product_id)
                    )
                ).scalar_one()
                product.current_stock = max(product.current_stock - cart_item.quantity, 0)
                if product.current_stock == 0:
                    product.stock_status = StockStatus.OUT_OF_STOCK

                db.add(
                    EcommerceOrderItem(
                        order_id=order.id,
                        product_id=cart_item.product_id,
                        shop_id=shop_id,
                        quantity=cart_item.quantity,
                        unit_price=cart_item.unit_price,
                        discount=cart_item.discount,
                        discount_type=cart_item.discount_type,
                        product_name=cart_item.product_name,
                        product_slug=cart_item.product_slug,
                        product_thumbnail=cart_item.product_thumbnail,
                    )
                )
            created_order_ids.append(order.id)

        if coupon and customer_id:
            await EcommerceCouponService.record_usage(
                db, coupon.id, customer_id, order_group_id
            )

        owner_filter = EcommerceCartService._owner_filter(owner)
        checked_ids = [item.id for item in items]
        await db.execute(
            delete(EcommerceCartItem).where(
                *owner_filter,
                EcommerceCartItem.id.in_(checked_ids),
            )
        )
        await EcommerceShippingService.clear_for_owner(db, owner)
        await db.flush()
        return created_order_ids

    @staticmethod
    async def checkout_total(
        db: AsyncSession,
        owner: CartOwnerContext,
        coupon_code: str | None = None,
    ) -> Decimal:
        items = await EcommerceOrderService._load_checked_cart(db, owner)
        cart_groups = {item.cart_group_id for item in items}
        shipping_map = await EcommerceShippingService.require_shipping_for_groups(
            db, owner, cart_groups
        )
        coupon, coupon_split = await EcommerceOrderService._resolve_coupon(
            db, owner, coupon_code, shipping_map
        )
        is_free_delivery = coupon and coupon.coupon_type.value == "free_delivery"
        grouped: dict[UUID, list[EcommerceCartItem]] = defaultdict(list)
        for item in items:
            grouped[item.shop_id].append(item)

        total = Decimal("0")
        for shop_id, shop_items in grouped.items():
            shipping = shipping_map.get(shop_id) or shipping_map.get(shop_items[0].cart_group_id)
            shipping_cost = Decimal("0") if is_free_delivery else (
                shipping.shipping_cost if shipping else Decimal("0")
            )
            shop_coupon_discount = coupon_split.get(shop_id, Decimal("0"))
            order_amount, _, _, _ = await EcommerceOrderService._totals_for_group(
                shop_items, shipping_cost, coupon_discount=shop_coupon_discount
            )
            total += order_amount
        return total

    @staticmethod
    async def place_cod_order(
        db: AsyncSession,
        owner: CartOwnerContext,
        address_id: UUID | None = None,
        order_note: str | None = None,
        coupon_code: str | None = None,
    ) -> dict:
        order_ids = await EcommerceOrderService.generate_orders_from_cart(
            db,
            owner,
            payment_method=EcommercePaymentMethod.CASH_ON_DELIVERY,
            order_status=EcommerceOrderStatus.PENDING,
            payment_status=EcommercePaymentStatus.UNPAID,
            address_id=address_id,
            order_note=order_note,
            coupon_code=coupon_code,
        )
        orders = (
            await db.execute(
                select(EcommerceOrder).where(EcommerceOrder.id.in_(order_ids))
            )
        ).scalars().all()
        await EcommerceOrderService._notify_order_placed(db, list(orders))
        return {
            "order_ids": [order.id for order in orders],
            "order_numbers": [order.public_id for order in orders],
            "new_user": False,
        }

    @staticmethod
    async def create_payment_request(
        db: AsyncSession,
        owner: CartOwnerContext,
        payer_email: str,
        payer_name: str,
        payer_phone: str | None,
        address_id: UUID | None = None,
        order_note: str | None = None,
        coupon_code: str | None = None,
    ) -> EcommercePaymentRequest:
        total = await EcommerceOrderService.checkout_total(db, owner, coupon_code=coupon_code)
        payment = EcommercePaymentRequest(
            owner_id=owner.owner_id,
            is_guest=owner.is_guest,
            payment_amount=total,
            currency_code="UGX",
            payer_information=PesapalService.payer_json(payer_email, payer_name, payer_phone),
            additional_data=json.dumps(
                {
                    "address_id": str(address_id) if address_id else None,
                    "order_note": order_note,
                    "coupon_code": coupon_code,
                }
            ),
        )
        db.add(payment)
        await db.flush()
        return payment

    @staticmethod
    async def fulfill_payment_request(
        db: AsyncSession,
        payment: EcommercePaymentRequest,
        transaction_ref: str,
    ) -> list[UUID]:
        if payment.is_paid:
            return [UUID(value) for value in payment.order_ids()]

        owner = CartOwnerContext(owner_id=payment.owner_id, is_guest=payment.is_guest)
        additional = payment.additional()
        address_id = UUID(additional["address_id"]) if additional.get("address_id") else None
        order_note = additional.get("order_note")
        coupon_code = additional.get("coupon_code")

        order_ids = await EcommerceOrderService.generate_orders_from_cart(
            db,
            owner,
            payment_method=EcommercePaymentMethod.PESAPAL,
            order_status=EcommerceOrderStatus.CONFIRMED,
            payment_status=EcommercePaymentStatus.PAID,
            transaction_ref=transaction_ref,
            address_id=address_id,
            order_note=order_note,
            paid_amount=payment.payment_amount,
            coupon_code=coupon_code,
        )
        payment.is_paid = True
        payment.transaction_id = transaction_ref
        payment.order_ids_json = json.dumps([str(order_id) for order_id in order_ids])
        await db.flush()
        orders = (
            await db.execute(select(EcommerceOrder).where(EcommerceOrder.id.in_(order_ids)))
        ).scalars().all()
        await EcommerceOrderService._notify_order_placed(db, list(orders))
        return order_ids

    @staticmethod
    async def _serialize_order(order: EcommerceOrder, items: list[EcommerceOrderItem]) -> dict:
        return {
            "id": str(order.id),
            "order_id": order.public_id,
            "order_group_id": str(order.order_group_id),
            "shop_id": str(order.shop_id),
            "order_status": order.order_status.value,
            "payment_status": order.payment_status.value,
            "payment_method": order.payment_method.value,
            "order_amount": float(order.order_amount),
            "shipping_cost": float(order.shipping_cost),
            "discount_amount": float(order.discount_amount),
            "tax_amount": float(order.tax_amount),
            "paid_amount": float(order.paid_amount),
            "currency": order.currency,
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
    async def list_orders(db: AsyncSession, customer_id: UUID) -> list[dict]:
        orders = (
            await db.execute(
                select(EcommerceOrder)
                .where(
                    EcommerceOrder.customer_id == customer_id,
                    EcommerceOrder.deleted_at.is_(None),
                )
                .order_by(EcommerceOrder.created_at.desc())
            )
        ).scalars().all()
        result = []
        for order in orders:
            items = (
                await db.execute(
                    select(EcommerceOrderItem).where(
                        EcommerceOrderItem.order_id == order.id,
                        EcommerceOrderItem.deleted_at.is_(None),
                    )
                )
            ).scalars().all()
            result.append(await EcommerceOrderService._serialize_order(order, items))
        return result

    @staticmethod
    async def get_order_details(
        db: AsyncSession,
        owner: CartOwnerContext,
        order_id: UUID,
    ) -> dict:
        query = select(EcommerceOrder).where(
            EcommerceOrder.id == order_id,
            EcommerceOrder.deleted_at.is_(None),
        )
        if owner.is_guest:
            query = query.where(
                EcommerceOrder.guest_id == owner.owner_id,
                EcommerceOrder.is_guest.is_(True),
            )
        else:
            query = query.where(EcommerceOrder.customer_id == owner.owner_id)
        order = (await db.execute(query)).scalar_one_or_none()
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
        return await EcommerceOrderService._serialize_order(order, items)

    @staticmethod
    async def _notify_order_placed(db: AsyncSession, orders: list[EcommerceOrder]) -> None:
        from app.models.ecommerce.accounts import CustomerAccount
        from app.services.ecommerce.notification_service import EcommerceNotificationService

        if not orders or not orders[0].customer_id:
            return
        customer = await db.get(CustomerAccount, orders[0].customer_id)
        if not customer:
            return
        numbers = ", ".join(o.public_id for o in orders)
        total = sum(o.order_amount for o in orders)
        await EcommerceNotificationService.notify_customer(
            db,
            customer_id=customer.id,
            title="Order placed successfully",
            body=f"Your order(s) {numbers} totaling UGX {total:,.0f} have been placed.",
            notification_type="order_placed",
            reference_id=orders[0].order_group_id,
            email=customer.email,
        )

    @staticmethod
    async def cancel_order(db: AsyncSession, owner: CartOwnerContext, order_id: UUID) -> str:
        query = select(EcommerceOrder).where(
            EcommerceOrder.id == order_id,
            EcommerceOrder.deleted_at.is_(None),
        )
        if owner.is_guest:
            query = query.where(EcommerceOrder.guest_id == owner.owner_id)
        else:
            query = query.where(EcommerceOrder.customer_id == owner.owner_id)
        order = (await db.execute(query)).scalar_one_or_none()
        if not order:
            raise AppError(404, "Order not found", "order_not_found")

        cancellable_statuses = {EcommerceOrderStatus.PENDING, EcommerceOrderStatus.CONFIRMED}
        if order.order_status not in cancellable_statuses:
            raise AppError(403, "Order status not changeable now", "status_not_changeable")
        if order.payment_method == EcommercePaymentMethod.CASH_ON_DELIVERY:
            if order.order_status != EcommerceOrderStatus.PENDING:
                raise AppError(403, "Order status not changeable now", "status_not_changeable")

        group_orders = (
            await db.execute(
                select(EcommerceOrder).where(
                    EcommerceOrder.order_group_id == order.order_group_id,
                    EcommerceOrder.deleted_at.is_(None),
                )
            )
        ).scalars().all()
        refund_total = Decimal("0")
        for group_order in group_orders:
            if group_order.payment_status == EcommercePaymentStatus.PAID:
                refund_total += group_order.paid_amount or group_order.order_amount
            items = (
                await db.execute(
                    select(EcommerceOrderItem).where(EcommerceOrderItem.order_id == group_order.id)
                )
            ).scalars().all()
            for item in items:
                product = (
                    await db.execute(
                        select(EcommerceProduct).where(EcommerceProduct.id == item.product_id)
                    )
                ).scalar_one_or_none()
                if product:
                    product.current_stock += item.quantity
                    if product.stock_status == StockStatus.OUT_OF_STOCK and product.current_stock > 0:
                        product.stock_status = StockStatus.IN_STOCK
            group_order.order_status = EcommerceOrderStatus.CANCELED
            if group_order.payment_status == EcommercePaymentStatus.PAID:
                group_order.payment_status = EcommercePaymentStatus.REFUNDED

        if refund_total > 0 and order.customer_id:
            from app.services.ecommerce.wallet_service import EcommerceWalletService

            await EcommerceWalletService.refund_order(
                db, order.customer_id, refund_total, order.public_id
            )
        await db.flush()
        return "order_canceled_successfully"

    @staticmethod
    async def place_wallet_order(
        db: AsyncSession,
        owner: CartOwnerContext,
        address_id: UUID | None = None,
        order_note: str | None = None,
        coupon_code: str | None = None,
    ) -> dict:
        if owner.is_guest:
            raise AppError(401, "Login required for wallet payment", "unauthorized")

        total = await EcommerceOrderService.checkout_total(db, owner, coupon_code=coupon_code)
        balance = await EcommerceWalletService.get_balance(db, owner.owner_id)
        if balance < total:
            raise AppError(400, "Insufficient wallet balance", "insufficient_balance")

        order_ids = await EcommerceOrderService.generate_orders_from_cart(
            db,
            owner,
            payment_method=EcommercePaymentMethod.WALLET,
            order_status=EcommerceOrderStatus.CONFIRMED,
            payment_status=EcommercePaymentStatus.PAID,
            address_id=address_id,
            order_note=order_note,
            paid_amount=total,
            coupon_code=coupon_code,
        )
        await EcommerceWalletService.debit_order_payment(db, owner.owner_id, total)
        orders = (
            await db.execute(select(EcommerceOrder).where(EcommerceOrder.id.in_(order_ids)))
        ).scalars().all()
        await EcommerceOrderService._notify_order_placed(db, list(orders))
        return {
            "order_ids": [order.id for order in orders],
            "order_numbers": [order.public_id for order in orders],
            "new_user": False,
        }

    @staticmethod
    async def resolve_payer(db: AsyncSession, owner: CartOwnerContext) -> tuple[str, str, str | None]:
        if owner.is_guest:
            return "guest@checkout.local", "Guest Customer", None
        account = (
            await db.execute(
                select(CustomerAccount).where(
                    CustomerAccount.id == owner.owner_id,
                    CustomerAccount.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if not account:
            raise AppError(401, "Customer not found", "unauthorized")
        name = f"{account.first_name} {account.last_name}".strip()
        return account.email, name, account.phone
