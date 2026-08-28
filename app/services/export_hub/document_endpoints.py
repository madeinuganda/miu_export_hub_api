"""Shared helpers for endpoints that stream generated PDFs."""

from __future__ import annotations

from uuid import UUID

from fastapi import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.shared.exceptions import AppError
from app.models.export_hub.orders import Order
from app.models.export_hub.rfqs import Rfq, RfqQuote
from app.services.export_hub.deal_documents import (
    build_order_attachment,
    build_quote_attachment,
    build_rfq_attachment,
)
from app.services.shared.notifications.email_templates import EmailAttachment


def _pdf_response(attachment: EmailAttachment | None) -> Response:
    if attachment is None:
        raise AppError(503, "Document generation is unavailable", "documents_unavailable")
    return Response(
        content=attachment.content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{attachment.filename}"'},
    )


async def _resolve_rfq(db: AsyncSession, public_id: str) -> Rfq:
    suffix = public_id.replace("DEAL-", "", 1) if public_id.startswith("DEAL-") else public_id
    rfq_public = public_id if public_id.startswith("RFQ-") else f"RFQ-{suffix}"
    rfq = (
        await db.execute(
            select(Rfq).where(Rfq.public_id == rfq_public, Rfq.deleted_at.is_(None))
        )
    ).scalar_one_or_none()
    if not rfq:
        raise AppError(404, "RFQ not found", "not_found")
    return rfq


async def _latest_quote(db: AsyncSession, rfq_id: UUID) -> RfqQuote:
    quote = (
        await db.execute(
            select(RfqQuote)
            .where(RfqQuote.rfq_id == rfq_id, RfqQuote.deleted_at.is_(None))
            .order_by(RfqQuote.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if not quote:
        raise AppError(404, "No quote on this RFQ yet", "not_found")
    return quote


class AdminDocuments:
    pdf_response = staticmethod(_pdf_response)

    @staticmethod
    async def rfq_document_response(
        db: AsyncSession, public_id: str, doc_kind: str
    ) -> Response:
        rfq = await _resolve_rfq(db, public_id)
        kind = doc_kind.replace(".pdf", "").strip().lower()
        if kind == "rfq":
            return _pdf_response(await build_rfq_attachment(db, rfq))
        if kind in ("quote", "quotation"):
            quote = await _latest_quote(db, rfq.id)
            return _pdf_response(await build_quote_attachment(db, rfq, quote))
        raise AppError(404, "Unknown document type", "not_found")

    @staticmethod
    async def order_document_response(db: AsyncSession, public_id: str) -> Response:
        order = (
            await db.execute(
                select(Order).where(Order.public_id == public_id, Order.deleted_at.is_(None))
            )
        ).scalar_one_or_none()
        if not order:
            raise AppError(404, "Order not found", "not_found")
        return _pdf_response(await build_order_attachment(db, order))


class ScopedDocuments:
    """Buyer/supplier variants that enforce ownership before generating."""

    @staticmethod
    async def rfq_document_response(
        db: AsyncSession,
        public_id: str,
        doc_kind: str,
        *,
        buyer_org_id: UUID | None = None,
        supplier_org_id: UUID | None = None,
    ) -> Response:
        rfq = await _resolve_rfq(db, public_id)
        if buyer_org_id and rfq.buyer_org_id != buyer_org_id:
            raise AppError(404, "RFQ not found", "not_found")
        if supplier_org_id and rfq.supplier_org_id != supplier_org_id:
            raise AppError(404, "RFQ not found", "not_found")

        kind = doc_kind.replace(".pdf", "").strip().lower()
        if kind == "rfq":
            return _pdf_response(await build_rfq_attachment(db, rfq))
        if kind in ("quote", "quotation"):
            if buyer_org_id:
                # Buyers only get the quote once MIU has relayed it.
                from app.services.export_hub.rfq_service import RfqService

                quote = await RfqService.buyer_visible_quote(db, rfq.id)
                if not quote:
                    raise AppError(404, "No quote available yet", "not_found")
            else:
                quote = await _latest_quote(db, rfq.id)
            return _pdf_response(await build_quote_attachment(db, rfq, quote))
        raise AppError(404, "Unknown document type", "not_found")

    @staticmethod
    async def order_document_response(
        db: AsyncSession,
        public_id: str,
        *,
        buyer_org_id: UUID | None = None,
        supplier_org_id: UUID | None = None,
    ) -> Response:
        query = select(Order).where(
            Order.public_id == public_id, Order.deleted_at.is_(None)
        )
        if buyer_org_id:
            query = query.where(Order.buyer_org_id == buyer_org_id)
        if supplier_org_id:
            query = query.where(Order.supplier_org_id == supplier_org_id)
        order = (await db.execute(query)).scalar_one_or_none()
        if not order:
            raise AppError(404, "Order not found", "not_found")
        return _pdf_response(await build_order_attachment(db, order))
