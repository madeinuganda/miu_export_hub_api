from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.export_hub.organizations import BuyerOrganization, SupplierOrganization
from app.models.export_hub.orders import Order
from app.models.export_hub.payments import PaymentEscrow
from app.models.export_hub.rfqs import Rfq, RfqQuote
from app.models.shared.enums import (
    EscrowStatus,
    OrderStatus,
    QuoteStatus,
    RfqStatus,
    SenderRole,
)
from app.services.export_hub.admin_service import AdminService
from app.services.export_hub.order_service import OrderService, PIPELINE_STAGE_IDS
from app.services.export_hub.payment_service import PaymentService
from app.services.export_hub.rfq_service import RfqService


def _stage_needs_supplier_action(pipeline_index: int) -> bool:
    if pipeline_index < 0 or pipeline_index >= len(PIPELINE_STAGE_IDS):
        return False
    return PIPELINE_STAGE_IDS[pipeline_index] in ("in_production", "ready_to_dispatch")


def _thread_needs_reply(
    msgs: list,
    viewer: SenderRole,
    *,
    last_read_at=None,
) -> bool:
    if not msgs:
        return False
    last = msgs[-1]
    from app.models.shared.enums import MessageReviewStatus

    if last.review_status != MessageReviewStatus.ROUTED:
        return False
    if viewer == SenderRole.SUPPLIER:
        needs = last.sender_role in (SenderRole.BUYER, SenderRole.ADMIN)
    elif viewer == SenderRole.BUYER:
        needs = last.sender_role in (SenderRole.SUPPLIER, SenderRole.ADMIN)
    else:
        return False
    if not needs:
        return False
    # Viewing the thread clears the badge until a newer inbound message arrives.
    if last_read_at is not None and last.sent_at is not None and last.sent_at <= last_read_at:
        return False
    return True


class NavBadgesService:
    @staticmethod
    async def _count_threads_needing_reply(db: AsyncSession, rfq_ids: list[UUID], viewer: SenderRole) -> int:
        unique_ids = list(dict.fromkeys(rfq_ids))
        count = 0
        for rfq_id in unique_ids:
            rfq = await db.get(Rfq, rfq_id)
            if not rfq or rfq.deleted_at:
                continue
            msgs = await RfqService._rfq_messages(db, rfq_id)
            last_read_at = (
                rfq.supplier_messages_read_at
                if viewer == SenderRole.SUPPLIER
                else rfq.buyer_messages_read_at
            )
            if _thread_needs_reply(msgs, viewer, last_read_at=last_read_at):
                count += 1
        return count

    @staticmethod
    async def _supplier_pending_payments(db: AsyncSession, org_id: UUID) -> int:
        rows = (
            await db.execute(
                select(PaymentEscrow, Order)
                .join(Order, Order.id == PaymentEscrow.order_id)
                .where(
                    Order.supplier_org_id == org_id,
                    PaymentEscrow.deleted_at.is_(None),
                    Order.deleted_at.is_(None),
                    PaymentEscrow.status != EscrowStatus.PENDING,
                )
            )
        ).all()
        delivered_index = PaymentService._delivered_pipeline_index()
        count = 0
        for escrow, order in rows:
            milestones = await PaymentService._milestones_for_escrow(db, escrow.id)
            balance_milestone = milestones.get("balance")
            pipeline_index = OrderService.order_pipeline_index(order)
            balance_pending = PaymentService._balance_status(escrow, balance_milestone) == "pending_delivery"
            if balance_pending and pipeline_index >= delivered_index:
                count += 1
        return count

    @staticmethod
    async def _admin_escrow_release_count(db: AsyncSession) -> int:
        rows = (
            await db.execute(
                select(PaymentEscrow, Order)
                .join(Order, Order.id == PaymentEscrow.order_id)
                .where(
                    PaymentEscrow.deleted_at.is_(None),
                    Order.deleted_at.is_(None),
                    PaymentEscrow.status != EscrowStatus.PENDING,
                    Order.status != OrderStatus.FULFILLED.value,
                )
            )
        ).all()
        delivered_index = PaymentService._delivered_pipeline_index()
        count = 0
        for escrow, order in rows:
            milestones = await PaymentService._milestones_for_escrow(db, escrow.id)
            balance_milestone = milestones.get("balance")
            pipeline_index = OrderService.order_pipeline_index(order)
            balance_pending = PaymentService._balance_status(escrow, balance_milestone) == "pending_delivery"
            if balance_pending and pipeline_index >= delivered_index:
                count += 1
        return count

    @staticmethod
    async def admin_badges(db: AsyncSession) -> dict:
        rfqs = (
            await db.execute(select(Rfq).where(Rfq.deleted_at.is_(None)))
        ).scalars().all()

        new_rfqs = 0
        rfq_pending_threads = 0
        deal_pending_threads = 0

        for rfq in rfqs:
            routed = await AdminService._rfq_assigned(db, rfq.id)
            admin_status = AdminService._rfq_admin_status(rfq, routed)
            pending = await RfqService.pending_message_count(db, rfq.id)

            if admin_status == "new":
                new_rfqs += 1

            quote = (
                await db.execute(
                    select(RfqQuote)
                    .where(RfqQuote.rfq_id == rfq.id, RfqQuote.deleted_at.is_(None))
                    .limit(1)
                )
            ).scalar_one_or_none()
            order = (
                await db.execute(
                    select(Order).where(Order.rfq_id == rfq.id, Order.deleted_at.is_(None)).limit(1)
                )
            ).scalar_one_or_none()
            has_deal = quote is not None or order is not None

            if pending > 0:
                if has_deal:
                    deal_pending_threads += 1
                else:
                    rfq_pending_threads += 1

        verification_pending = 0
        suppliers = (
            await db.execute(
                select(SupplierOrganization).where(SupplierOrganization.deleted_at.is_(None))
            )
        ).scalars().all()
        for org in suppliers:
            status = await AdminService.effective_verification_status(db, org)
            if status in ("pending", "action_required"):
                verification_pending += 1

        buyers_pending = 0
        buyer_orgs = (
            await db.execute(select(BuyerOrganization).where(BuyerOrganization.deleted_at.is_(None)))
        ).scalars().all()
        for org in buyer_orgs:
            if AdminService._buyer_review_status(org) in ("pending", "action_required"):
                buyers_pending += 1

        orders = await NavBadgesService._admin_escrow_release_count(db)
        rfq_queue = new_rfqs + rfq_pending_threads
        deal_relay = deal_pending_threads
        verification = verification_pending
        buyers = buyers_pending
        unread_count = rfq_queue + deal_relay + verification + buyers + orders

        return {
            "unread_count": unread_count,
            "rfq_queue": rfq_queue,
            "deal_relay": deal_relay,
            "orders": orders,
            "verification": verification,
            "buyers": buyers,
        }

    @staticmethod
    async def supplier_badges(db: AsyncSession, org_id: UUID) -> dict:
        rfqs = (
            await db.execute(
                select(Rfq).where(Rfq.supplier_org_id == org_id, Rfq.deleted_at.is_(None))
            )
        ).scalars().all()

        new_rfqs = 0
        rfq_ids: list[UUID] = []
        for rfq in rfqs:
            rfq_ids.append(rfq.id)
            if await RfqService.supplier_inbox_status(rfq, db) == "new":
                new_rfqs += 1

        orders = (
            await db.execute(
                select(Order).where(
                    Order.supplier_org_id == org_id,
                    Order.deleted_at.is_(None),
                    Order.status != OrderStatus.FULFILLED.value,
                )
            )
        ).scalars().all()

        order_rfq_ids: list[UUID] = []
        orders_action = 0
        for order in orders:
            order_rfq_ids.append(await RfqService.resolve_rfq_id_for_order(db, order))
            if _stage_needs_supplier_action(OrderService.order_pipeline_index(order)):
                orders_action += 1

        messages = await NavBadgesService._count_threads_needing_reply(
            db, rfq_ids + order_rfq_ids, SenderRole.SUPPLIER
        )
        payments = await NavBadgesService._supplier_pending_payments(db, org_id)
        total = new_rfqs + messages + orders_action + payments

        return {
            "total": total,
            "rfq": new_rfqs,
            "orders": orders_action,
            "messages": messages,
            "payments": payments,
        }

    @staticmethod
    async def buyer_badges(db: AsyncSession, buyer_org_id: UUID) -> dict:
        rfqs = (
            await db.execute(
                select(Rfq).where(Rfq.buyer_org_id == buyer_org_id, Rfq.deleted_at.is_(None))
            )
        ).scalars().all()

        rfq_action = 0
        rfq_ids: list[UUID] = []
        for rfq in rfqs:
            rfq_ids.append(rfq.id)
            if rfq.status != RfqStatus.RESPONDED:
                continue
            quote = (
                await db.execute(
                    select(RfqQuote)
                    .where(
                        RfqQuote.rfq_id == rfq.id,
                        RfqQuote.deleted_at.is_(None),
                        RfqQuote.status == QuoteStatus.SENT,
                    )
                    .limit(1)
                )
            ).scalar_one_or_none()
            if quote:
                rfq_action += 1

        orders = (
            await db.execute(
                select(Order).where(
                    Order.buyer_org_id == buyer_org_id,
                    Order.deleted_at.is_(None),
                    Order.status != OrderStatus.FULFILLED.value,
                )
            )
        ).scalars().all()

        order_rfq_ids = [
            await RfqService.resolve_rfq_id_for_order(db, order) for order in orders
        ]
        messages = await NavBadgesService._count_threads_needing_reply(
            db, rfq_ids + order_rfq_ids, SenderRole.BUYER
        )

        return {
            "rfqs": rfq_action,
            "messages": messages,
            "orders": 0,
            "total": rfq_action + messages,
        }
