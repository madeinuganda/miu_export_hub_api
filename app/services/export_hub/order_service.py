from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.shared.exceptions import AppError
from app.models.export_hub.catalog import Product
from app.models.shared.enums import EscrowStatus, MilestoneState, OrderStatus, PaymentMilestoneStatus, QuoteStatus, RfqStatus
from app.models.export_hub.orders import Order, OrderActivity, OrderMilestone, OrderTracking
from app.models.export_hub.organizations import SupplierOrganization
from app.models.export_hub.payments import PaymentEscrow, PaymentLink, PaymentMilestone
from app.models.export_hub.rfqs import Rfq, RfqQuote
from app.services.export_hub.rfq_service import RfqService
from app.utils.audit import apply_create_audit, apply_update_audit
from app.utils.formatting import format_quantity, format_ugx

BUYER_STEPS = [
    ("order_placed", "Order Placed"),
    ("production", "Production"),
    ("quality_check", "Quality Check"),
    ("shipped", "Shipped"),
    ("delivered", "Delivered"),
]


class OrderService:
    @staticmethod
    async def _next_order_id(db: AsyncSession) -> str:
        year = datetime.now(timezone.utc).year
        count = (
            await db.execute(select(func.count()).select_from(Order).where(Order.public_id.like(f"MIU-ORD-{year}-%")))
        ).scalar() or 0
        return f"MIU-ORD-{year}-{count + 1:03d}"

    @staticmethod
    async def accept_rfq(db: AsyncSession, buyer_org_id: UUID, user_id: UUID, public_id: str) -> dict:
        rfq = (
            await db.execute(select(Rfq).where(Rfq.public_id == public_id, Rfq.buyer_org_id == buyer_org_id, Rfq.deleted_at.is_(None)))
        ).scalar_one_or_none()
        if not rfq:
            raise AppError(404, "RFQ not found", "not_found")
        quote = (
            await db.execute(
                select(RfqQuote).where(RfqQuote.rfq_id == rfq.id, RfqQuote.status == QuoteStatus.SENT.value, RfqQuote.deleted_at.is_(None)).limit(1)
            )
        ).scalar_one_or_none()
        if not quote:
            raise AppError(400, "No quote to accept", "no_quote")
        product = await db.get(Product, rfq.product_id)
        total = quote.unit_price * rfq.quantity
        order = Order(
            public_id=await OrderService._next_order_id(db),
            buyer_org_id=buyer_org_id,
            supplier_org_id=rfq.supplier_org_id,
            product_id=rfq.product_id,
            rfq_id=rfq.id,
            quantity=rfq.quantity,
            unit=rfq.unit,
            total_value_amount=total,
            currency=quote.currency,
            status=OrderStatus.PAYMENT_SECURED,
            tone=product.tone if product else "coffee",
        )
        apply_create_audit(order, user_id)
        db.add(order)
        await db.flush()
        for i, (key, label) in enumerate(BUYER_STEPS):
            state = MilestoneState.COMPLETE if i == 0 else MilestoneState.UPCOMING if i > 1 else MilestoneState.CURRENT
            db.add(
                OrderMilestone(
                    order_id=order.id,
                    step_key=key,
                    label=label,
                    state=state,
                    sort_order=i,
                    created_by=user_id,
                    updated_by=user_id,
                )
            )
        db.add(
            OrderActivity(
                order_id=order.id,
                occurred_at=datetime.now(timezone.utc),
                description="Order placed — trade assurance payment secured.",
                created_by=user_id,
                updated_by=user_id,
            )
        )
        upfront = total * Decimal("0.7")
        balance = total - upfront
        escrow = PaymentEscrow(
            order_id=order.id,
            total_amount=total,
            currency=quote.currency,
            upfront_percent=70,
            upfront_amount=upfront,
            balance_amount=balance,
            status=EscrowStatus.UPFRONT_RECEIVED,
            created_by=user_id,
            updated_by=user_id,
        )
        db.add(escrow)
        await db.flush()
        token = str(uuid4())
        db.add(
            PaymentLink(
                escrow_id=escrow.id,
                token=token,
                expires_at=datetime.now(timezone.utc) + timedelta(days=7),
                created_by=user_id,
                updated_by=user_id,
            )
        )
        db.add(
            PaymentMilestone(
                escrow_id=escrow.id,
                milestone_type="upfront",
                amount=upfront,
                status=PaymentMilestoneStatus.RECEIVED,
                created_by=user_id,
                updated_by=user_id,
            )
        )
        rfq.status = RfqStatus.ACCEPTED
        quote.status = QuoteStatus.ACCEPTED
        apply_update_audit(rfq, user_id)
        apply_update_audit(quote, user_id)
        return {"orderId": order.public_id, "paymentLinkToken": token}

    @staticmethod
    async def _serialize_order_listing(db: AsyncSession, order: Order, tab: str) -> dict:
        product = await db.get(Product, order.product_id)
        supplier = await db.get(SupplierOrganization, order.supplier_org_id)
        milestones = (
            await db.execute(
                select(OrderMilestone)
                .where(OrderMilestone.order_id == order.id, OrderMilestone.deleted_at.is_(None))
                .order_by(OrderMilestone.sort_order)
            )
        ).scalars().all()
        filled = sum(1 for m in milestones if m.state == MilestoneState.COMPLETE)
        current = next((m for m in milestones if m.state == MilestoneState.CURRENT), milestones[0] if milestones else None)
        img = None
        if product:
            from app.models.export_hub.catalog import ProductImage
            img_row = (
                await db.execute(
                    select(ProductImage.url).where(ProductImage.product_id == product.id, ProductImage.is_primary.is_(True)).limit(1)
                )
            ).scalar_one_or_none()
            img = img_row
        return {
            "id": order.public_id,
            "productName": product.name if product else "",
            "supplierName": supplier.name if supplier else "",
            "quantity": format_quantity(order.quantity, order.unit),
            "totalValue": format_ugx(order.total_value_amount),
            "tab": tab,
            "progressLabel": current.label if current else "",
            "progressFilled": filled,
            "progressTotal": len(milestones) or 4,
            "tone": order.tone or "coffee",
            "image": img,
        }

    @staticmethod
    async def list_buyer_orders(db: AsyncSession, buyer_org_id: UUID, tab: str | None = None) -> list[dict]:
        orders = (
            await db.execute(select(Order).where(Order.buyer_org_id == buyer_org_id, Order.deleted_at.is_(None)).order_by(Order.created_at.desc()))
        ).scalars().all()
        items = []
        for o in orders:
            is_completed = o.status in (OrderStatus.DELIVERED, OrderStatus.FULFILLED)
            order_tab = "completed" if is_completed else "active"
            if tab and tab != order_tab:
                continue
            items.append(await OrderService._serialize_order_listing(db, o, order_tab))
        return items

    @staticmethod
    async def get_buyer_order_detail(db: AsyncSession, buyer_org_id: UUID, public_id: str) -> dict:
        order = (
            await db.execute(select(Order).where(Order.public_id == public_id, Order.buyer_org_id == buyer_org_id, Order.deleted_at.is_(None)))
        ).scalar_one_or_none()
        if not order:
            raise AppError(404, "Order not found", "not_found")
        listing = await OrderService._serialize_order_listing(
            db, order, "completed" if order.status in (OrderStatus.DELIVERED, OrderStatus.FULFILLED) else "active"
        )
        milestones = (
            await db.execute(select(OrderMilestone).where(OrderMilestone.order_id == order.id, OrderMilestone.deleted_at.is_(None)).order_by(OrderMilestone.sort_order))
        ).scalars().all()
        activity = (
            await db.execute(select(OrderActivity).where(OrderActivity.order_id == order.id, OrderActivity.deleted_at.is_(None)).order_by(OrderActivity.occurred_at.desc()))
        ).scalars().all()
        tracking = (
            await db.execute(select(OrderTracking).where(OrderTracking.order_id == order.id, OrderTracking.deleted_at.is_(None)).limit(1))
        ).scalar_one_or_none()
        escrow = (
            await db.execute(select(PaymentEscrow).where(PaymentEscrow.order_id == order.id, PaymentEscrow.deleted_at.is_(None)).limit(1))
        ).scalar_one_or_none()
        upfront = escrow.upfront_amount if escrow else Decimal(0)
        return {
            **listing,
            "paidAmount": format_ugx(upfront),
            "paidPercentLabel": "70% paid",
            "eta": tracking.eta_date.isoformat() if tracking and tracking.eta_date else "",
            "trackingNumber": tracking.tracking_number if tracking else None,
            "steps": [{"id": m.step_key, "label": m.label, "state": m.state.value} for m in milestones],
            "activity": [{"date": a.occurred_at.date().isoformat(), "text": a.description} for a in activity],
        }
