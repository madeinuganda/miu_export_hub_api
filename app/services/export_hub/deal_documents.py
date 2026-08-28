"""Turn RFQ / quote / order / payment rows into branded PDF attachments.

Keeps the party and line-item assembly in one place so the RFQ, order and
payment services all produce consistent documents.
"""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.export_hub.accounts import BuyerAccount, SupplierAccount
from app.models.export_hub.catalog import Product
from app.models.export_hub.orders import Order, OrderPaymentProof
from app.models.export_hub.organizations import (
    BuyerOrganization,
    BuyerOrganizationMember,
    SupplierOrganization,
    SupplierOrganizationMember,
)
from app.models.export_hub.payments import PaymentEscrow
from app.models.export_hub.rfqs import Rfq, RfqQuote
from app.models.shared.enums import PAYMENT_PROOF_TYPE_LABELS
from app.services.shared.document_service import (
    format_doc_date,
    order_document,
    payment_receipt_document,
    quotation_document,
    rfq_document,
)
from app.services.shared.notifications.email_templates import EmailAttachment
from app.utils.formatting import format_money, format_quantity

logger = logging.getLogger(__name__)


def payment_type_label(payment_type: str) -> str:
    return PAYMENT_PROOF_TYPE_LABELS.get(payment_type, "Payment")


async def _buyer_party_lines(db: AsyncSession, org_id: UUID) -> list[str]:
    org = await db.get(BuyerOrganization, org_id)
    lines: list[str] = [org.name] if org else []
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
    if member:
        account = await db.get(BuyerAccount, member.buyer_account_id)
        if account:
            name = " ".join(x for x in (account.first_name, account.last_name) if x)
            if name:
                lines.append(name)
            if account.email:
                lines.append(account.email)
    if org:
        location = ", ".join(x for x in (org.city, org.country) if x)
        if location:
            lines.append(location)
    return lines or ["Buyer"]


async def _supplier_party_lines(db: AsyncSession, org_id: UUID) -> list[str]:
    org = await db.get(SupplierOrganization, org_id)
    lines: list[str] = [org.name] if org else []
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
    if member:
        account = await db.get(SupplierAccount, member.supplier_account_id)
        if account and account.email:
            lines.append(account.email)
    if org:
        location = ", ".join(x for x in (org.district, org.region) if x)
        lines.append(location or "Uganda")
    return lines or ["Supplier"]


async def build_rfq_attachment(db: AsyncSession, rfq: Rfq) -> EmailAttachment | None:
    product = await db.get(Product, rfq.product_id)
    return rfq_document(
        reference=rfq.public_id,
        issued_on=format_doc_date(rfq.sent_at or rfq.created_at),
        buyer_lines=await _buyer_party_lines(db, rfq.buyer_org_id),
        supplier_lines=await _supplier_party_lines(db, rfq.supplier_org_id),
        product_name=product.name if product else "Product",
        quantity_label=format_quantity(rfq.quantity, rfq.unit),
        destination=rfq.destination_port,
        target_price=(
            format_money(rfq.target_price_amount, rfq.target_price_currency, rfq.unit)
            if rfq.target_price_amount
            else None
        ),
        incoterm=rfq.incoterm,
        needed_by=format_doc_date(rfq.required_by_date) if rfq.required_by_date else None,
        requirements=rfq.message,
    )


async def build_quote_attachment(
    db: AsyncSession, rfq: Rfq, quote: RfqQuote
) -> EmailAttachment | None:
    product = await db.get(Product, rfq.product_id)
    total = quote.unit_price * rfq.quantity
    suffix = rfq.public_id.replace("RFQ-", "", 1)
    return quotation_document(
        reference=rfq.public_id,
        quote_reference=f"QTN-{suffix}",
        issued_on=format_doc_date(quote.sent_at or quote.submitted_at or quote.created_at),
        valid_until=None,
        buyer_lines=await _buyer_party_lines(db, rfq.buyer_org_id),
        supplier_lines=await _supplier_party_lines(db, rfq.supplier_org_id),
        product_name=product.name if product else "Product",
        quantity_label=format_quantity(rfq.quantity, rfq.unit),
        unit_price=format_money(quote.unit_price, quote.currency, rfq.unit),
        total_price=format_money(total, quote.currency),
        incoterm=quote.incoterm or rfq.incoterm,
        lead_time=f"{quote.lead_time_days} days" if quote.lead_time_days else None,
        shipment_terms=quote.shipment_terms,
        notes=quote.notes,
    )


async def build_order_attachment(db: AsyncSession, order: Order) -> EmailAttachment | None:
    product = await db.get(Product, order.product_id)
    escrow = (
        await db.execute(
            select(PaymentEscrow)
            .where(PaymentEscrow.order_id == order.id, PaymentEscrow.deleted_at.is_(None))
            .limit(1)
        )
    ).scalar_one_or_none()
    quote = None
    rfq = await db.get(Rfq, order.rfq_id) if order.rfq_id else None
    if order.rfq_id:
        quote = (
            await db.execute(
                select(RfqQuote)
                .where(RfqQuote.rfq_id == order.rfq_id, RfqQuote.deleted_at.is_(None))
                .order_by(RfqQuote.updated_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
    currency = order.currency
    unit_price = (
        format_money(quote.unit_price, quote.currency, order.unit) if quote else None
    )
    return order_document(
        reference=order.public_id,
        issued_on=format_doc_date(order.created_at),
        status=order.status.value.replace("_", " ").title(),
        buyer_lines=await _buyer_party_lines(db, order.buyer_org_id),
        supplier_lines=await _supplier_party_lines(db, order.supplier_org_id),
        product_name=product.name if product else "Product",
        quantity_label=format_quantity(order.quantity, order.unit),
        unit_price=unit_price,
        total_value=format_money(order.total_value_amount, currency),
        upfront=format_money(escrow.upfront_amount, escrow.currency or currency)
        if escrow
        else None,
        balance=format_money(escrow.balance_amount, escrow.currency or currency)
        if escrow
        else None,
        incoterm=quote.incoterm if quote and quote.incoterm else (rfq.incoterm if rfq else None),
        lead_time=f"{quote.lead_time_days} days" if quote and quote.lead_time_days else None,
        rfq_reference=rfq.public_id if rfq else None,
    )


async def build_payment_proof_attachment(
    db: AsyncSession, order: Order, proof: OrderPaymentProof
) -> EmailAttachment | None:
    product = await db.get(Product, order.product_id)
    return payment_receipt_document(
        reference=proof.reference_no,
        order_reference=order.public_id,
        issued_on=format_doc_date(proof.created_at),
        payment_type_label=payment_type_label(proof.payment_type),
        amount=format_money(proof.amount, proof.currency),
        method=proof.method,
        payment_reference=proof.payment_reference,
        paid_at=format_doc_date(proof.paid_at) if proof.paid_at else None,
        buyer_lines=await _buyer_party_lines(db, order.buyer_org_id),
        supplier_lines=await _supplier_party_lines(db, order.supplier_org_id),
        product_name=product.name if product else "Product",
        order_total=format_money(order.total_value_amount, order.currency),
        note=proof.note,
    )
