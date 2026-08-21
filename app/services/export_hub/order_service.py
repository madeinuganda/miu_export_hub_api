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
from app.models.export_hub.organizations import BuyerOrganization, SupplierOrganization
from app.models.export_hub.payments import PaymentEscrow, PaymentLink, PaymentMilestone
from app.models.export_hub.rfqs import Rfq, RfqQuote
from app.services.export_hub.rfq_service import RfqService
from app.utils.audit import apply_create_audit, apply_update_audit, soft_delete
from app.utils.formatting import format_money, format_quantity


def _format_display_date(value: datetime | None) -> str:
    if not value:
        return ""
    return f"{value.day} {value.strftime('%b %Y')}"

# Canonical order lifecycle, shared by admin, supplier, and buyer views alike so
# every role reads/writes the same `order_milestones` rows and never disagrees
# about where an order stands.
ORDER_PIPELINE: list[tuple[str, str, OrderStatus]] = [
    ("confirmed", "Confirmed", OrderStatus.ORDER_PLACED),
    ("payment_secured", "Payment Secured", OrderStatus.PAYMENT_SECURED),
    ("in_production", "In Production", OrderStatus.IN_PRODUCTION),
    ("ready_to_dispatch", "Ready to Dispatch", OrderStatus.QUALITY_CHECK),
    ("shipped", "Shipped", OrderStatus.SHIPPED),
    ("delivered", "Delivered", OrderStatus.DELIVERED),
    ("fulfilled", "Fulfilled", OrderStatus.FULFILLED),
]

PIPELINE_STAGE_IDS = [s[0] for s in ORDER_PIPELINE]
PIPELINE_BY_STAGE = {stage_id: (i, label, status) for i, (stage_id, label, status) in enumerate(ORDER_PIPELINE)}
ORDER_STATUS_TO_STAGE = {status: stage for stage, _, status in ORDER_PIPELINE}

# Backward-compatible alias — admin_service.py historically owned this constant.
ADMIN_PIPELINE = ORDER_PIPELINE

# Coarser 4-bucket status shown on the supplier order list/filters.
SUPPLIER_STAGE_TO_STATUS = {
    "confirmed": "payment_secured",
    "payment_secured": "payment_secured",
    "in_production": "in_production",
    "ready_to_dispatch": "in_production",
    "shipped": "shipped",
    "delivered": "fulfilled",
    "fulfilled": "fulfilled",
}


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
            await db.execute(
                select(Rfq)
                .where(
                    Rfq.public_id == public_id,
                    Rfq.buyer_org_id == buyer_org_id,
                    Rfq.deleted_at.is_(None),
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if not rfq:
            raise AppError(404, "RFQ not found", "not_found")
        if rfq.status not in (RfqStatus.RESPONDED, RfqStatus.AWAITING):
            raise AppError(400, "RFQ cannot be accepted in its current status", "invalid_status")
        quote = (
            await db.execute(
                select(RfqQuote)
                .where(
                    RfqQuote.rfq_id == rfq.id,
                    RfqQuote.status == QuoteStatus.SENT.value,
                    RfqQuote.deleted_at.is_(None),
                )
                .limit(1)
                .with_for_update()
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
            status=OrderStatus.ORDER_PLACED,
            tone=product.tone if product else "coffee",
        )
        apply_create_audit(order, user_id)
        db.add(order)
        await db.flush()
        await OrderService.sync_pipeline_milestones(
            db, order, PIPELINE_BY_STAGE["confirmed"][0], user_id
        )
        db.add(
            OrderActivity(
                order_id=order.id,
                occurred_at=datetime.now(timezone.utc),
                description="Order created — awaiting trade assurance payment.",
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
            status=EscrowStatus.PENDING,
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
                status=PaymentMilestoneStatus.PENDING,
                created_by=user_id,
                updated_by=user_id,
            )
        )
        db.add(
            PaymentMilestone(
                escrow_id=escrow.id,
                milestone_type="balance",
                amount=balance,
                status=PaymentMilestoneStatus.PENDING,
                created_by=user_id,
                updated_by=user_id,
            )
        )
        rfq.status = RfqStatus.ACCEPTED
        quote.status = QuoteStatus.ACCEPTED
        apply_update_audit(rfq, user_id)
        apply_update_audit(quote, user_id)
        from app.services.export_hub.rfq_service import RfqService

        await RfqService.notify_supplier_quote_accepted(
            db,
            rfq,
            order_public_id=order.public_id,
            offered_price=format_money(quote.unit_price, quote.currency, rfq.unit),
        )
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
            "totalValue": format_money(order.total_value_amount, order.currency),
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
        paid_percent = escrow.upfront_percent if escrow else 0
        if escrow and escrow.status == EscrowStatus.BALANCE_RELEASED:
            paid_percent = 100
        return {
            **listing,
            "paidAmount": format_money(
                upfront, (escrow.currency if escrow else None) or order.currency
            ),
            "paidPercentLabel": f"{paid_percent}% paid",
            "eta": tracking.eta_date.isoformat() if tracking and tracking.eta_date else "",
            "trackingNumber": tracking.tracking_number if tracking else None,
            "steps": [{"id": m.step_key, "label": m.label, "state": m.state.value} for m in milestones],
            "activity": [{"date": a.occurred_at.date().isoformat(), "text": a.description} for a in activity],
        }

    # ------------------------------------------------------------------
    # Shared pipeline helpers (used by admin + supplier order views)
    # ------------------------------------------------------------------

    @staticmethod
    def pipeline_stages() -> list[dict]:
        return [
            {"id": stage_id, "label": label, "index": i}
            for i, (stage_id, label, _) in enumerate(ORDER_PIPELINE)
        ]

    @staticmethod
    def order_pipeline_index(order: Order) -> int:
        stage = ORDER_STATUS_TO_STAGE.get(order.status, "confirmed")
        return PIPELINE_BY_STAGE[stage][0]

    @staticmethod
    async def sync_pipeline_milestones(
        db: AsyncSession,
        order: Order,
        target_index: int,
        actor_id: UUID,
    ) -> list[OrderMilestone]:
        existing = (
            await db.execute(
                select(OrderMilestone).where(
                    OrderMilestone.order_id == order.id,
                    OrderMilestone.deleted_at.is_(None),
                )
            )
        ).scalars().all()
        by_key = {m.step_key: m for m in existing}
        synced: list[OrderMilestone] = []

        for i, (stage_id, label, _) in enumerate(ORDER_PIPELINE):
            if i < target_index:
                state = MilestoneState.COMPLETE
            elif i == target_index:
                state = MilestoneState.CURRENT
            else:
                state = MilestoneState.UPCOMING

            milestone = by_key.get(stage_id)
            if milestone:
                milestone.label = label
                milestone.state = state
                milestone.sort_order = i
                apply_update_audit(milestone, actor_id)
                synced.append(milestone)
            else:
                milestone = OrderMilestone(
                    order_id=order.id,
                    step_key=stage_id,
                    label=label,
                    state=state,
                    sort_order=i,
                    created_by=actor_id,
                    updated_by=actor_id,
                )
                db.add(milestone)
                synced.append(milestone)

        for milestone in existing:
            if milestone.step_key not in PIPELINE_STAGE_IDS:
                soft_delete(milestone, actor_id)

        await db.flush()
        return sorted(synced, key=lambda m: m.sort_order)

    # ------------------------------------------------------------------
    # Supplier order views
    # ------------------------------------------------------------------

    @staticmethod
    def _coarse_supplier_status(stage_id: str) -> str:
        return SUPPLIER_STAGE_TO_STATUS.get(stage_id, "payment_secured")

    @staticmethod
    async def _supplier_payment_note(
        db: AsyncSession, order: Order, pipeline_index: int
    ) -> tuple[str, str]:
        escrow = (
            await db.execute(
                select(PaymentEscrow).where(PaymentEscrow.order_id == order.id, PaymentEscrow.deleted_at.is_(None)).limit(1)
            )
        ).scalar_one_or_none()
        if not escrow:
            return "Payment pending", "muted"
        if escrow.status == EscrowStatus.PENDING:
            return "Awaiting escrow payment", "muted"
        if escrow.status == EscrowStatus.BALANCE_RELEASED:
            return "Fully paid", "positive"
        if pipeline_index >= PIPELINE_BY_STAGE["delivered"][0]:
            return "Fully paid", "positive"
        if pipeline_index >= PIPELINE_BY_STAGE["in_production"][0]:
            return f"{format_money(escrow.balance_amount, escrow.currency or order.currency)} due", "muted"
        return "Escrow secured", "muted"

    @staticmethod
    async def serialize_supplier_order_listing(db: AsyncSession, order: Order) -> dict:
        product = await db.get(Product, order.product_id)
        buyer = await db.get(BuyerOrganization, order.buyer_org_id)
        pipeline_index = OrderService.order_pipeline_index(order)
        payment_note, payment_tone = await OrderService._supplier_payment_note(db, order, pipeline_index)
        return {
            "id": order.public_id,
            "date": _format_display_date(order.created_at),
            "country": (buyer.country if buyer and buyer.country else "") or "N/A",
            "product": product.name if product else "N/A",
            "quantity": format_quantity(order.quantity, order.unit),
            "value": format_money(order.total_value_amount, order.currency),
            "paymentNote": payment_note,
            "paymentTone": payment_tone,
            "status": OrderService._coarse_supplier_status(PIPELINE_STAGE_IDS[pipeline_index]),
            "pipelineStage": PIPELINE_STAGE_IDS[pipeline_index],
        }

    @staticmethod
    async def _order_incoterm(db: AsyncSession, order: Order) -> str:
        if order.rfq_id:
            quote = (
                await db.execute(
                    select(RfqQuote)
                    .where(RfqQuote.rfq_id == order.rfq_id, RfqQuote.supplier_org_id == order.supplier_org_id, RfqQuote.deleted_at.is_(None))
                    .order_by(RfqQuote.updated_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if quote and quote.incoterm:
                return quote.incoterm
        return "FOB Mombasa"

    @staticmethod
    async def _supplier_owned_order(db: AsyncSession, supplier_org_id: UUID, public_id: str) -> Order:
        order = (
            await db.execute(
                select(Order).where(
                    Order.public_id == public_id,
                    Order.supplier_org_id == supplier_org_id,
                    Order.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if not order:
            raise AppError(404, "Order not found", "not_found")
        return order

    @staticmethod
    async def get_supplier_order_detail(db: AsyncSession, supplier_org_id: UUID, public_id: str) -> dict:
        order = await OrderService._supplier_owned_order(db, supplier_org_id, public_id)
        listing = await OrderService.serialize_supplier_order_listing(db, order)
        pipeline_index = OrderService.order_pipeline_index(order)

        buyer = await db.get(BuyerOrganization, order.buyer_org_id)
        milestones = (
            await db.execute(
                select(OrderMilestone)
                .where(OrderMilestone.order_id == order.id, OrderMilestone.deleted_at.is_(None))
                .order_by(OrderMilestone.sort_order)
            )
        ).scalars().all()
        activity = (
            await db.execute(
                select(OrderActivity)
                .where(OrderActivity.order_id == order.id, OrderActivity.deleted_at.is_(None))
                .order_by(OrderActivity.occurred_at.desc())
            )
        ).scalars().all()
        tracking = (
            await db.execute(
                select(OrderTracking).where(OrderTracking.order_id == order.id, OrderTracking.deleted_at.is_(None)).limit(1)
            )
        ).scalar_one_or_none()
        escrow = (
            await db.execute(
                select(PaymentEscrow).where(PaymentEscrow.order_id == order.id, PaymentEscrow.deleted_at.is_(None)).limit(1)
            )
        ).scalar_one_or_none()

        milestone_state_map = {
            MilestoneState.COMPLETE: "done",
            MilestoneState.CURRENT: "current",
            MilestoneState.UPCOMING: "upcoming",
        }
        can_advance = PIPELINE_STAGE_IDS[pipeline_index] == "in_production"

        fulfilled_index = PIPELINE_BY_STAGE["fulfilled"][0]
        buyer_label = buyer.name if buyer and pipeline_index >= fulfilled_index else "Verified Buyer"

        if tracking and (tracking.carrier or tracking.tracking_number):
            shipping_headline = f"In transit via {tracking.carrier}" if tracking.carrier else "Shipment in transit"
            eta_text = f" ETA {tracking.eta_date.isoformat()}." if tracking.eta_date else ""
            tracking_text = f" Tracking: {tracking.tracking_number}." if tracking.tracking_number else ""
            shipping_note = f"{tracking_text}{eta_text}".strip() or "Tracking details shared with buyer."
        elif pipeline_index >= PIPELINE_BY_STAGE["delivered"][0]:
            shipping_headline = "Delivered to buyer"
            shipping_note = "Proof of delivery confirmed. Order complete."
        else:
            shipping_headline = "Logistics not yet arranged"
            shipping_note = "MIU will confirm shipping details once goods are ready for dispatch."

        escrow_legs = []
        if escrow:
            upfront_secured = escrow.status != EscrowStatus.PENDING
            balance_released = escrow.status == EscrowStatus.BALANCE_RELEASED
            currency = escrow.currency or order.currency
            escrow_legs.append(
                {
                    "label": f"{escrow.upfront_percent}% upfront (escrow)",
                    "amount": format_money(escrow.upfront_amount, currency),
                    "note": _format_display_date(order.created_at) if upfront_secured else "Awaiting payment",
                    "secured": upfront_secured,
                }
            )
            escrow_legs.append(
                {
                    "label": f"{100 - escrow.upfront_percent}% on delivery",
                    "amount": format_money(escrow.balance_amount, currency),
                    "note": "Released on delivery confirmation" if balance_released else "Due on delivery",
                    "secured": balance_released,
                }
            )
        else:
            currency = order.currency
            escrow_legs = [
                {
                    "label": "70% upfront (escrow)",
                    "amount": format_money(order.total_value_amount * Decimal("0.7"), currency),
                    "note": "Awaiting payment setup",
                    "secured": False,
                },
                {
                    "label": "30% on delivery",
                    "amount": format_money(order.total_value_amount * Decimal("0.3"), currency),
                    "note": "Due on delivery",
                    "secured": False,
                },
            ]

        # Production milestones: prefer stored rows; otherwise derive from pipeline.
        if milestones:
            milestone_items = [
                {"id": m.step_key, "label": m.label, "state": milestone_state_map.get(m.state, "upcoming")}
                for m in milestones
            ]
        else:
            production_labels = [
                ("raw-materials", "Raw materials acquired"),
                ("processing", "Processing begun"),
                ("quality", "Quality inspection"),
                ("packaging", "Packaging complete"),
                ("collection", "Ready for collection"),
            ]
            if pipeline_index < PIPELINE_BY_STAGE["in_production"][0]:
                milestone_items = [
                    {"id": k, "label": label, "state": "current" if i == 0 else "upcoming"}
                    for i, (k, label) in enumerate(production_labels)
                ]
            elif pipeline_index >= PIPELINE_BY_STAGE["ready_to_dispatch"][0]:
                milestone_items = [
                    {"id": k, "label": label, "state": "done"} for k, label in production_labels
                ]
            else:
                # Mid production — mark first two done, third current
                milestone_items = []
                for i, (k, label) in enumerate(production_labels):
                    if i < 2:
                        state = "done"
                    elif i == 2:
                        state = "current"
                    else:
                        state = "upcoming"
                    milestone_items.append({"id": k, "label": label, "state": state})

        timeline = [
            {"date": _format_display_date(a.occurred_at), "description": a.description} for a in activity
        ]
        if not timeline:
            timeline = [
                {
                    "date": _format_display_date(order.created_at),
                    "description": "Order confirmed by MIU",
                }
            ]

        return {
            **listing,
            "incoterm": await OrderService._order_incoterm(db, order),
            "buyerLabel": buyer_label,
            "timeline": timeline,
            "milestones": milestone_items,
            "milestoneProgress": round((pipeline_index / (len(ORDER_PIPELINE) - 1)) * 100),
            "milestoneCaption": (
                "Click Update to mark production complete once goods are ready to dispatch."
                if can_advance
                else "MIU coordinates shipping and payment release once production is complete."
            ),
            "shippingHeadline": shipping_headline,
            "shippingNote": shipping_note,
            "escrow": escrow_legs,
            "pipelineStage": PIPELINE_STAGE_IDS[pipeline_index],
            "canAdvance": can_advance,
        }

    @staticmethod
    async def advance_supplier_order(db: AsyncSession, supplier_org_id: UUID, public_id: str, actor_id: UUID) -> dict:
        order = await OrderService._supplier_owned_order(db, supplier_org_id, public_id)
        pipeline_index = OrderService.order_pipeline_index(order)
        if PIPELINE_STAGE_IDS[pipeline_index] != "in_production":
            raise AppError(
                400,
                "Order must be In Production before it can be marked ready to dispatch",
                "invalid_transition",
            )

        target_index = pipeline_index + 1
        _, target_label, target_status = ORDER_PIPELINE[target_index]
        order.status = target_status
        apply_update_audit(order, actor_id)
        await OrderService.sync_pipeline_milestones(db, order, target_index, actor_id)
        db.add(
            OrderActivity(
                order_id=order.id,
                occurred_at=datetime.now(timezone.utc),
                description=f"Supplier marked production complete — order is now {target_label}.",
                created_by=actor_id,
                updated_by=actor_id,
            )
        )
        return await OrderService.get_supplier_order_detail(db, supplier_org_id, public_id)
