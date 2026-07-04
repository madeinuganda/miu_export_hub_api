from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.shared.exceptions import AppError
from app.models.export_hub.catalog import Product
from app.models.shared.enums import ProductStatus, QuoteStatus, RfqStatus, SenderRole
from app.models.export_hub.organizations import BuyerOrganization, SupplierOrganization
from app.models.export_hub.rfqs import Rfq, RfqMessage, RfqQuote
from app.utils.audit import apply_create_audit, apply_update_audit
from app.utils.formatting import format_quantity, format_ugx


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
        awaiting = sum(1 for i in items if i["status"] == "awaiting")
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
                    "time": "recent",
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
        return {"status": "quote_sent"}

    @staticmethod
    async def add_message(db: AsyncSession, rfq_id: UUID, role: SenderRole, body: str, user_id: UUID | None) -> None:
        msg = RfqMessage(rfq_id=rfq_id, sender_role=role, body=body, sent_at=datetime.now(timezone.utc))
        apply_create_audit(msg, user_id)
        db.add(msg)
