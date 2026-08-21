from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.shared.config import get_settings
from app.core.shared.exceptions import AppError
from app.models.export_hub.accounts import BuyerAccount, SupplierAccount
from app.models.export_hub.catalog import Product
from app.models.shared.enums import MessageReviewStatus, ProductStatus, QuoteStatus, RfqStatus, SenderRole
from app.models.export_hub.organizations import (
    BuyerOrganization,
    BuyerOrganizationMember,
    SupplierOrganization,
    SupplierOrganizationMember,
)
from app.models.export_hub.rfqs import Rfq, RfqMessage, RfqQuote
from app.services.shared.email_service import EmailService
from app.utils.audit import apply_create_audit, apply_update_audit
from app.utils.formatting import format_quantity, format_relative_time, format_money, format_ugx

OTHER_PARTY_ROLE = {
    SenderRole.BUYER: SenderRole.SUPPLIER,
    SenderRole.SUPPLIER: SenderRole.BUYER,
}


class CreateRfqRequest(BaseModel):
    product_id: UUID
    quantity: Decimal
    unit: str
    target_price_amount: Decimal | None = None
    target_price_currency: str = "UGX"
    incoterm: str | None = None
    destination_port: str | None = None
    required_by: str | None = None
    message: str | None = None
    supplier_org_id: UUID | None = None
    sample_requested: bool = False


class SubmitQuoteRequest(BaseModel):
    unit_price: Decimal
    currency: str = "UGX"
    incoterm: str | None = None
    lead_time_days: int | None = None
    shipment_terms: str | None = None
    notes: str | None = None


class RfqService:
    @staticmethod
    def _parse_required_by(value: str | None) -> date | None:
        if not value or not value.strip():
            return None
        try:
            return date.fromisoformat(value.strip()[:10])
        except ValueError:
            return None

    @staticmethod
    async def _next_rfq_id(db: AsyncSession) -> str:
        year = datetime.now(timezone.utc).year
        count = (
            await db.execute(select(func.count()).select_from(Rfq).where(Rfq.public_id.like(f"RFQ-{year}-%")))
        ).scalar() or 0
        return f"RFQ-{year}-{count + 1:03d}"

    @staticmethod
    async def create_rfq(db: AsyncSession, buyer_org_id: UUID, user_id: UUID, data: CreateRfqRequest) -> Rfq:
        product = await db.get(Product, data.product_id)
        if not product or product.deleted_at or product.status != ProductStatus.PUBLISHED:
            raise AppError(404, "Product not found", "not_found")
        supplier_org_id = data.supplier_org_id or product.supplier_org_id
        rfq = Rfq(
            public_id=await RfqService._next_rfq_id(db),
            buyer_org_id=buyer_org_id,
            product_id=product.id,
            supplier_org_id=supplier_org_id,
            quantity=data.quantity,
            unit=data.unit,
            target_price_amount=data.target_price_amount,
            target_price_currency=data.target_price_currency,
            incoterm=data.incoterm,
            destination_port=data.destination_port,
            required_by_date=RfqService._parse_required_by(data.required_by),
            message=data.message,
            status=RfqStatus.AWAITING,
            sample_requested=data.sample_requested,
            sent_at=datetime.now(timezone.utc),
        )
        apply_create_audit(rfq, user_id)
        db.add(rfq)
        await db.flush()
        if data.message and data.message.strip():
            await RfqService.add_message(db, rfq.id, SenderRole.BUYER, data.message.strip(), user_id)
        await RfqService.notify_supplier_new_rfq(db, rfq)
        return rfq

    @staticmethod
    async def _serialize_buyer_listing(db: AsyncSession, rfq: Rfq) -> dict:
        product = await db.get(Product, rfq.product_id)
        supplier = await db.get(SupplierOrganization, rfq.supplier_org_id)
        quote = (
            await db.execute(
                select(RfqQuote).where(RfqQuote.rfq_id == rfq.id, RfqQuote.deleted_at.is_(None)).order_by(RfqQuote.created_at.desc()).limit(1)
            )
        ).scalar_one_or_none()
        status_map = {
            RfqStatus.AWAITING: "awaiting",
            RfqStatus.RESPONDED: "responded",
            RfqStatus.ACCEPTED: "accepted",
            RfqStatus.DECLINED: "declined",
        }
        return {
            "id": rfq.public_id,
            "status": status_map.get(rfq.status, "awaiting"),
            "productName": product.name if product else "",
            "supplierName": supplier.name if supplier else "via MIU",
            "quantity": format_quantity(rfq.quantity, rfq.unit),
            "targetPrice": format_ugx(rfq.target_price_amount or 0, rfq.unit) if rfq.target_price_amount else "",
            "sentDate": rfq.sent_at.date().isoformat() if rfq.sent_at else "",
            "offeredPrice": format_ugx(quote.unit_price, rfq.unit) if quote else None,
            "destination": rfq.destination_port or "",
            "supplierResponse": quote.notes if quote else None,
        }

    @staticmethod
    async def list_buyer_rfqs(db: AsyncSession, buyer_org_id: UUID) -> dict:
        rfqs = (
            await db.execute(select(Rfq).where(Rfq.buyer_org_id == buyer_org_id, Rfq.deleted_at.is_(None)).order_by(Rfq.sent_at.desc()))
        ).scalars().all()
        items = [await RfqService._serialize_buyer_listing(db, r) for r in rfqs]
        awaiting = sum(1 for i in items if i["status"] == "responded")
        return {"items": items, "summary": {"total": len(items), "awaitingYourResponse": awaiting}}

    @staticmethod
    async def get_buyer_rfq(db: AsyncSession, buyer_org_id: UUID, public_id: str) -> dict:
        rfq = (
            await db.execute(select(Rfq).where(Rfq.public_id == public_id, Rfq.buyer_org_id == buyer_org_id, Rfq.deleted_at.is_(None)))
        ).scalar_one_or_none()
        if not rfq:
            raise AppError(404, "RFQ not found", "not_found")
        return await RfqService._serialize_buyer_listing(db, rfq)

    @staticmethod
    async def supplier_inbox_status(rfq: Rfq, db: AsyncSession) -> str:
        quote = (
            await db.execute(select(RfqQuote).where(RfqQuote.rfq_id == rfq.id, RfqQuote.deleted_at.is_(None)).limit(1))
        ).scalar_one_or_none()
        if rfq.status == RfqStatus.ACCEPTED:
            return "accepted"
        if quote and quote.status in (QuoteStatus.SENT, QuoteStatus.ACCEPTED):
            return "quote_sent"
        return "new"

    @staticmethod
    async def list_supplier_rfqs(db: AsyncSession, org_id: UUID, status_filter: str | None) -> list[dict]:
        rfqs = (
            await db.execute(select(Rfq).where(Rfq.supplier_org_id == org_id, Rfq.deleted_at.is_(None)).order_by(Rfq.sent_at.desc()))
        ).scalars().all()
        items = []
        for rfq in rfqs:
            st = await RfqService.supplier_inbox_status(rfq, db)
            if status_filter and status_filter != "all" and st != status_filter:
                continue
            product = await db.get(Product, rfq.product_id)
            buyer = await db.get(BuyerOrganization, rfq.buyer_org_id)
            items.append(
                {
                    "id": rfq.public_id,
                    "product": product.name if product else "",
                    "route": f"via MIU Admin · {buyer.country if buyer else 'International'}",
                    "quantity": format_quantity(rfq.quantity, rfq.unit),
                    "time": format_relative_time(rfq.sent_at),
                    "status": st,
                    "sampleRequested": rfq.sample_requested,
                }
            )
        return items

    @staticmethod
    async def submit_quote(db: AsyncSession, org_id: UUID, user_id: UUID, public_id: str, data: SubmitQuoteRequest) -> dict:
        rfq = (
            await db.execute(select(Rfq).where(Rfq.public_id == public_id, Rfq.supplier_org_id == org_id, Rfq.deleted_at.is_(None)))
        ).scalar_one_or_none()
        if not rfq:
            raise AppError(404, "RFQ not found", "not_found")
        quote = RfqQuote(
            rfq_id=rfq.id,
            supplier_org_id=org_id,
            unit_price=data.unit_price,
            currency=data.currency,
            incoterm=data.incoterm,
            lead_time_days=data.lead_time_days,
            shipment_terms=data.shipment_terms,
            notes=data.notes,
            status=QuoteStatus.SENT,
            sent_at=datetime.now(timezone.utc),
        )
        apply_create_audit(quote, user_id)
        db.add(quote)
        rfq.status = RfqStatus.RESPONDED
        apply_update_audit(rfq, user_id)
        await db.flush()
        await RfqService.notify_buyer_quote_received(db, rfq, quote)
        return {"status": "quote_sent"}

    @staticmethod
    async def _primary_supplier_account(db: AsyncSession, org_id: UUID) -> SupplierAccount | None:
        member = (
            await db.execute(
                select(SupplierOrganizationMember)
                .where(
                    SupplierOrganizationMember.org_id == org_id,
                    SupplierOrganizationMember.deleted_at.is_(None),
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        if not member:
            return None
        return await db.get(SupplierAccount, member.supplier_account_id)

    @staticmethod
    async def _primary_buyer_account(db: AsyncSession, org_id: UUID) -> BuyerAccount | None:
        member = (
            await db.execute(
                select(BuyerOrganizationMember)
                .where(
                    BuyerOrganizationMember.org_id == org_id,
                    BuyerOrganizationMember.deleted_at.is_(None),
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        if not member:
            return None
        return await db.get(BuyerAccount, member.buyer_account_id)

    @staticmethod
    async def notify_supplier_new_rfq(
        db: AsyncSession,
        rfq: Rfq,
        *,
        note: str | None = None,
    ) -> None:
        account = await RfqService._primary_supplier_account(db, rfq.supplier_org_id)
        if not account or not account.email:
            return
        product = await db.get(Product, rfq.product_id)
        product_name = product.name if product else "Product"
        base = get_settings().frontend_base_url.rstrip("/")
        await EmailService.send_supplier_new_rfq_email(
            to_email=account.email,
            first_name=account.first_name or "there",
            rfq_public_id=rfq.public_id,
            product_name=product_name,
            quantity_label=format_quantity(rfq.quantity, rfq.unit),
            destination=rfq.destination_port,
            note=note,
            rfq_url=f"{base}/dashboard/supplier/rfq?id={rfq.public_id}",
        )

    @staticmethod
    async def notify_buyer_quote_received(db: AsyncSession, rfq: Rfq, quote: RfqQuote) -> None:
        account = await RfqService._primary_buyer_account(db, rfq.buyer_org_id)
        if not account or not account.email:
            return
        product = await db.get(Product, rfq.product_id)
        product_name = product.name if product else "Product"
        base = get_settings().frontend_base_url.rstrip("/")
        await EmailService.send_buyer_quote_received_email(
            to_email=account.email,
            first_name=account.first_name or "there",
            rfq_public_id=rfq.public_id,
            product_name=product_name,
            offered_price=format_ugx(quote.unit_price, rfq.unit),
            notes=quote.notes,
            rfq_url=f"{base}/dashboard/buyer/rfqs?id={rfq.public_id}",
        )

    @staticmethod
    async def notify_supplier_quote_accepted(
        db: AsyncSession,
        rfq: Rfq,
        *,
        order_public_id: str,
        offered_price: str,
    ) -> None:
        account = await RfqService._primary_supplier_account(db, rfq.supplier_org_id)
        if not account or not account.email:
            return
        product = await db.get(Product, rfq.product_id)
        product_name = product.name if product else "Product"
        base = get_settings().frontend_base_url.rstrip("/")
        await EmailService.send_supplier_quote_accepted_email(
            to_email=account.email,
            first_name=account.first_name or "there",
            rfq_public_id=rfq.public_id,
            order_public_id=order_public_id,
            product_name=product_name,
            quantity_label=format_quantity(rfq.quantity, rfq.unit),
            offered_price=offered_price,
            order_url=f"{base}/dashboard/supplier/orders/{order_public_id}",
        )

    @staticmethod
    async def notify_supplier_quote_declined(
        db: AsyncSession,
        rfq: Rfq,
        *,
        offered_price: str | None = None,
    ) -> None:
        account = await RfqService._primary_supplier_account(db, rfq.supplier_org_id)
        if not account or not account.email:
            return
        product = await db.get(Product, rfq.product_id)
        product_name = product.name if product else "Product"
        base = get_settings().frontend_base_url.rstrip("/")
        await EmailService.send_supplier_quote_declined_email(
            to_email=account.email,
            first_name=account.first_name or "there",
            rfq_public_id=rfq.public_id,
            product_name=product_name,
            offered_price=offered_price,
            rfq_url=f"{base}/dashboard/supplier/rfq?id={rfq.public_id}",
        )

    @staticmethod
    async def decline_buyer_rfq(
        db: AsyncSession,
        buyer_org_id: UUID,
        user_id: UUID,
        public_id: str,
    ) -> dict:
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
            raise AppError(400, "RFQ cannot be declined in its current status", "invalid_status")

        quote = (
            await db.execute(
                select(RfqQuote)
                .where(RfqQuote.rfq_id == rfq.id, RfqQuote.deleted_at.is_(None))
                .order_by(RfqQuote.created_at.desc())
                .limit(1)
                .with_for_update()
            )
        ).scalar_one_or_none()

        # Quote-declined emails only apply when a quote exists. AWAITING without a
        # quote is a buyer withdrawal — update status only, no quote notification.
        if rfq.status == RfqStatus.AWAITING and quote is None:
            rfq.status = RfqStatus.DECLINED
            apply_update_audit(rfq, user_id)
            return {"ok": True}

        if quote is None:
            raise AppError(400, "No quote to decline", "no_quote")
        if quote.status != QuoteStatus.SENT:
            raise AppError(400, "Quote cannot be declined in its current status", "invalid_status")

        offered_price = format_money(quote.unit_price, quote.currency, rfq.unit)
        quote.status = QuoteStatus.DECLINED
        apply_update_audit(quote, user_id)

        rfq.status = RfqStatus.DECLINED
        apply_update_audit(rfq, user_id)
        await RfqService.notify_supplier_quote_declined(db, rfq, offered_price=offered_price)
        return {"ok": True}

    @staticmethod
    async def add_message(
        db: AsyncSession,
        rfq_id: UUID,
        role: SenderRole,
        body: str,
        user_id: UUID | None,
        *,
        admin_note: str | None = None,
    ) -> RfqMessage:
        """Create a message on the deal thread. Buyer/supplier messages start
        PENDING (invisible to the other party until an admin routes them);
        admin/system messages are considered already reviewed."""
        review_status = (
            MessageReviewStatus.PENDING if role in (SenderRole.BUYER, SenderRole.SUPPLIER) else MessageReviewStatus.ROUTED
        )
        msg = RfqMessage(
            rfq_id=rfq_id,
            sender_role=role,
            body=body,
            sent_at=datetime.now(timezone.utc),
            review_status=review_status,
            admin_note=admin_note if review_status == MessageReviewStatus.ROUTED else None,
        )
        apply_create_audit(msg, user_id)
        db.add(msg)
        await db.flush()
        return msg

    @staticmethod
    def _serialize_message(m: RfqMessage, *, admin_view: bool) -> dict:
        item = {
            "id": str(m.id),
            "senderRole": m.sender_role.value,
            "body": m.body,
            "sentAt": m.sent_at.isoformat(),
            "reviewStatus": m.review_status.value,
        }
        if admin_view:
            item["adminNote"] = m.admin_note
            item["revertNote"] = m.revert_note
            item["reviewedAt"] = m.reviewed_at.isoformat() if m.reviewed_at else None
        else:
            if m.admin_note:
                item["adminNote"] = m.admin_note
            if m.review_status == MessageReviewStatus.REVERTED:
                item["revertNote"] = m.revert_note
        return item

    @staticmethod
    async def _rfq_messages(db: AsyncSession, rfq_id: UUID) -> list[RfqMessage]:
        return (
            await db.execute(
                select(RfqMessage)
                .where(RfqMessage.rfq_id == rfq_id, RfqMessage.deleted_at.is_(None))
                .order_by(RfqMessage.sent_at)
            )
        ).scalars().all()

    @staticmethod
    async def list_messages_for_viewer(db: AsyncSession, rfq_id: UUID, viewer_role: SenderRole) -> list[dict]:
        """Messages visible to a buyer or supplier viewer: their own messages
        (any review status, so they can see 'pending review' / 'reverted'
        badges on what they sent), plus routed admin/system messages, plus
        the other party's messages only once routed by an admin.

        Opening the thread marks it read for the viewer so nav message badges
        clear immediately until a newer inbound message arrives.
        """
        rows = await RfqService._rfq_messages(db, rfq_id)
        visible = []
        for m in rows:
            if m.sender_role == viewer_role:
                visible.append(m)
            elif m.review_status == MessageReviewStatus.ROUTED:
                visible.append(m)

        rfq = await db.get(Rfq, rfq_id)
        if rfq and not rfq.deleted_at:
            now = datetime.now(timezone.utc)
            if viewer_role == SenderRole.SUPPLIER:
                rfq.supplier_messages_read_at = now
            elif viewer_role == SenderRole.BUYER:
                rfq.buyer_messages_read_at = now

        return [RfqService._serialize_message(m, admin_view=False) for m in visible]

    @staticmethod
    async def list_messages_for_admin(db: AsyncSession, rfq_id: UUID) -> list[dict]:
        rows = await RfqService._rfq_messages(db, rfq_id)
        return [RfqService._serialize_message(m, admin_view=True) for m in rows]

    @staticmethod
    async def pending_message_count(db: AsyncSession, rfq_id: UUID) -> int:
        return (
            await db.execute(
                select(func.count()).select_from(RfqMessage).where(
                    RfqMessage.rfq_id == rfq_id,
                    RfqMessage.review_status == MessageReviewStatus.PENDING,
                    RfqMessage.deleted_at.is_(None),
                )
            )
        ).scalar() or 0

    @staticmethod
    async def route_message(
        db: AsyncSession, admin_id: UUID, rfq_id: UUID, message_id: UUID, note: str | None
    ) -> RfqMessage:
        msg = await db.get(RfqMessage, message_id)
        if not msg or msg.rfq_id != rfq_id or msg.deleted_at:
            raise AppError(404, "Message not found", "not_found")
        if msg.review_status != MessageReviewStatus.PENDING:
            raise AppError(400, "Message has already been reviewed", "invalid_status")
        msg.review_status = MessageReviewStatus.ROUTED
        msg.reviewed_at = datetime.now(timezone.utc)
        msg.reviewed_by = admin_id
        msg.admin_note = note
        apply_update_audit(msg, admin_id)
        return msg

    @staticmethod
    async def revert_message(
        db: AsyncSession, admin_id: UUID, rfq_id: UUID, message_id: UUID, remarks: str
    ) -> RfqMessage:
        msg = await db.get(RfqMessage, message_id)
        if not msg or msg.rfq_id != rfq_id or msg.deleted_at:
            raise AppError(404, "Message not found", "not_found")
        if msg.review_status != MessageReviewStatus.PENDING:
            raise AppError(400, "Message has already been reviewed", "invalid_status")
        msg.review_status = MessageReviewStatus.REVERTED
        msg.reviewed_at = datetime.now(timezone.utc)
        msg.reviewed_by = admin_id
        msg.revert_note = remarks
        apply_update_audit(msg, admin_id)
        return msg

    @staticmethod
    async def resolve_rfq_id_for_order(db: AsyncSession, order) -> UUID:
        if not order.rfq_id:
            raise AppError(400, "Order has no linked RFQ thread", "no_thread")
        return order.rfq_id
