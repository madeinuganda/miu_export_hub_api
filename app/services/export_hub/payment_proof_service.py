"""Admin-recorded proofs of payment against an order.

An order can carry many proofs (down payment, progressive payments, final
completion). Each proof either wraps a manually uploaded receipt or relies on a
MIU-generated receipt PDF, and carries its own flag for whether that document
is attached to the notification emails.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.shared.config import get_settings
from app.core.shared.exceptions import AppError
from app.models.export_hub.accounts import AdminAccount
from app.models.export_hub.misc import FileRecord
from app.models.export_hub.orders import Order, OrderActivity, OrderPaymentProof
from app.models.export_hub.payments import PaymentEscrow, PaymentMilestone
from app.models.shared.enums import (
    EscrowStatus,
    PaymentMilestoneStatus,
    PaymentProofType,
)
from app.schemas.export_hub.admin import (
    AdminPaymentProofItem,
    AdminPaymentProofListResponse,
    AdminPaymentProofRequest,
)
from app.services.export_hub.deal_documents import (
    build_payment_proof_attachment,
    payment_type_label,
)
from app.services.shared.email_service import EmailService
from app.services.shared.file_storage import public_file_url, store_upload_file
from app.utils.audit import apply_create_audit, apply_update_audit, soft_delete
from app.utils.formatting import format_money

logger = logging.getLogger(__name__)

# Which escrow leg a proof settles, when it maps to one.
MILESTONE_FOR_TYPE = {
    PaymentProofType.DOWN_PAYMENT.value: "upfront",
    PaymentProofType.FINAL_PAYMENT.value: "balance",
}


def _parse_paid_at(value: str | None) -> date | None:
    if not value or not str(value).strip():
        return None
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except ValueError as exc:
        raise AppError(422, "paid_at must be an ISO date (YYYY-MM-DD)", "validation_error") from exc


def _validate_type(value: str) -> str:
    try:
        return PaymentProofType(str(value).strip().lower()).value
    except ValueError as exc:
        allowed = ", ".join(t.value for t in PaymentProofType)
        raise AppError(422, f"payment_type must be one of: {allowed}", "validation_error") from exc


class PaymentProofService:
    @staticmethod
    async def _order(db: AsyncSession, public_id: str) -> Order:
        order = (
            await db.execute(
                select(Order).where(Order.public_id == public_id, Order.deleted_at.is_(None))
            )
        ).scalar_one_or_none()
        if not order:
            raise AppError(404, "Order not found", "not_found")
        return order

    @staticmethod
    async def _next_reference(db: AsyncSession, order: Order) -> str:
        count = (
            await db.execute(
                select(func.count())
                .select_from(OrderPaymentProof)
                .where(OrderPaymentProof.order_id == order.id)
            )
        ).scalar() or 0
        suffix = order.public_id.replace("MIU-ORD-", "", 1).replace("ORD-", "", 1)
        return f"POP-{suffix}-{count + 1:02d}"

    @staticmethod
    async def _proofs(db: AsyncSession, order: Order) -> list[OrderPaymentProof]:
        return list(
            (
                await db.execute(
                    select(OrderPaymentProof)
                    .where(
                        OrderPaymentProof.order_id == order.id,
                        OrderPaymentProof.deleted_at.is_(None),
                    )
                    .order_by(OrderPaymentProof.created_at)
                )
            ).scalars().all()
        )

    @staticmethod
    async def _serialize(
        db: AsyncSession, order: Order, proof: OrderPaymentProof
    ) -> AdminPaymentProofItem:
        file_url = None
        if proof.file_id:
            record = await db.get(FileRecord, proof.file_id)
            if record:
                file_url = public_file_url(record.storage_key)
        admin = await db.get(AdminAccount, proof.created_by) if proof.created_by else None
        recorded_by = None
        if admin:
            recorded_by = " ".join(x for x in (admin.first_name, admin.last_name) if x) or admin.email
        return AdminPaymentProofItem(
            id=proof.id,
            reference_no=proof.reference_no,
            payment_type=proof.payment_type,
            payment_type_label=payment_type_label(proof.payment_type),
            amount=proof.amount,
            amount_display=format_money(proof.amount, proof.currency),
            currency=proof.currency,
            method=proof.method,
            payment_reference=proof.payment_reference,
            paid_at=proof.paid_at.isoformat() if proof.paid_at else None,
            note=proof.note,
            file_url=file_url,
            file_name=proof.file_name,
            has_upload=bool(proof.file_id),
            receipt_url=(
                f"/api/v1/export-hub/admin/orders/{order.public_id}"
                f"/payment-proofs/{proof.id}/receipt"
            ),
            send_attachment=proof.send_attachment,
            notify_buyer=proof.notify_buyer,
            notify_supplier=proof.notify_supplier,
            notified_at=proof.notified_at,
            recorded_by=recorded_by,
            created_at=proof.created_at,
        )

    @staticmethod
    async def list_proofs(db: AsyncSession, public_id: str) -> AdminPaymentProofListResponse:
        order = await PaymentProofService._order(db, public_id)
        proofs = await PaymentProofService._proofs(db, order)
        recorded = sum(
            (p.amount for p in proofs if p.payment_type != PaymentProofType.REFUND.value),
            Decimal(0),
        )
        outstanding = max(order.total_value_amount - recorded, Decimal(0))
        return AdminPaymentProofListResponse(
            order_public_id=order.public_id,
            order_total_display=format_money(order.total_value_amount, order.currency),
            total_recorded=recorded,
            total_recorded_display=format_money(recorded, order.currency),
            outstanding_display=format_money(outstanding, order.currency),
            items=[await PaymentProofService._serialize(db, order, p) for p in proofs],
        )

    @staticmethod
    async def _apply_escrow_effects(
        db: AsyncSession, order: Order, proof: OrderPaymentProof, admin_id: UUID
    ) -> None:
        escrow = (
            await db.execute(
                select(PaymentEscrow)
                .where(PaymentEscrow.order_id == order.id, PaymentEscrow.deleted_at.is_(None))
                .limit(1)
            )
        ).scalar_one_or_none()
        if not escrow:
            return
        if escrow.status == EscrowStatus.PENDING:
            escrow.status = EscrowStatus.UPFRONT_RECEIVED
            apply_update_audit(escrow, admin_id)

        milestone_type = MILESTONE_FOR_TYPE.get(proof.payment_type)
        if not milestone_type:
            return
        milestone = (
            await db.execute(
                select(PaymentMilestone)
                .where(
                    PaymentMilestone.escrow_id == escrow.id,
                    PaymentMilestone.milestone_type == milestone_type,
                    PaymentMilestone.deleted_at.is_(None),
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        if milestone and milestone.status == PaymentMilestoneStatus.PENDING:
            milestone.status = PaymentMilestoneStatus.RECEIVED
            apply_update_audit(milestone, admin_id)

    @staticmethod
    async def create_proof(
        db: AsyncSession,
        admin: AdminAccount,
        public_id: str,
        data: AdminPaymentProofRequest,
        file: UploadFile | None = None,
    ) -> AdminPaymentProofItem:
        order = await PaymentProofService._order(db, public_id)
        payment_type = _validate_type(data.payment_type)
        if data.amount <= 0:
            raise AppError(422, "Amount must be greater than zero", "validation_error")

        proof = OrderPaymentProof(
            order_id=order.id,
            reference_no=await PaymentProofService._next_reference(db, order),
            payment_type=payment_type,
            amount=data.amount,
            currency=(data.currency or order.currency or "UGX").upper(),
            method=(data.method or "").strip() or None,
            payment_reference=(data.payment_reference or "").strip() or None,
            paid_at=_parse_paid_at(data.paid_at),
            note=(data.note or "").strip() or None,
            send_attachment=data.send_attachment,
            notify_buyer=data.notify_buyer,
            notify_supplier=data.notify_supplier,
        )
        apply_create_audit(proof, admin.id)

        if file is not None and file.filename:
            record = await store_upload_file(
                db,
                file=file,
                uploaded_by=admin.id,
                subdirectory=f"orders/{order.id}/payment-proofs",
            )
            proof.file_id = record.id
            proof.file_name = file.filename

        db.add(proof)
        await db.flush()

        await PaymentProofService._apply_escrow_effects(db, order, proof, admin.id)
        db.add(
            OrderActivity(
                order_id=order.id,
                occurred_at=datetime.now(timezone.utc),
                description=(
                    f"{payment_type_label(payment_type)} of "
                    f"{format_money(proof.amount, proof.currency)} recorded "
                    f"({proof.reference_no})."
                ),
                created_by=admin.id,
                updated_by=admin.id,
            )
        )
        await db.flush()

        await PaymentProofService.notify(db, order, proof)
        return await PaymentProofService._serialize(db, order, proof)

    @staticmethod
    async def build_attachment(db: AsyncSession, order: Order, proof: OrderPaymentProof):
        """The uploaded receipt when there is one, else a generated PDF."""
        if proof.file_id:
            record = await db.get(FileRecord, proof.file_id)
            if record:
                from pathlib import Path

                from app.services.shared.notifications.email_templates import EmailAttachment

                path = Path(get_settings().storage_path) / record.storage_key
                try:
                    content = path.read_bytes()
                except OSError:
                    logger.warning("Payment proof file missing on disk: %s", record.storage_key)
                    content = None
                if content:
                    return EmailAttachment(
                        filename=proof.file_name or path.name,
                        content=content,
                        mime_type=record.mime_type or "application/octet-stream",
                    )
        return await build_payment_proof_attachment(db, order, proof)

    @staticmethod
    async def notify(db: AsyncSession, order: Order, proof: OrderPaymentProof) -> None:
        from app.services.export_hub.rfq_service import RfqService

        if not (proof.notify_buyer or proof.notify_supplier):
            return

        attachment = None
        if proof.send_attachment:
            attachment = await PaymentProofService.build_attachment(db, order, proof)
        attachments = [attachment] if attachment else None

        base = get_settings().frontend_base_url.rstrip("/")
        label = payment_type_label(proof.payment_type)
        amount = format_money(proof.amount, proof.currency)
        paid_at = proof.paid_at.strftime("%d %b %Y") if proof.paid_at else None

        if proof.notify_buyer:
            buyer = await RfqService._primary_buyer_account(db, order.buyer_org_id)
            if buyer and buyer.email:
                await EmailService.send_payment_proof_email(
                    to_email=buyer.email,
                    first_name=buyer.first_name or "there",
                    order_public_id=order.public_id,
                    payment_type_label=label,
                    amount=amount,
                    reference=proof.payment_reference,
                    paid_at=paid_at,
                    method=proof.method,
                    note=proof.note,
                    order_url=f"{base}/dashboard/buyer/orders/{order.public_id}",
                    attachments=attachments,
                )
        if proof.notify_supplier:
            supplier = await RfqService._primary_supplier_account(db, order.supplier_org_id)
            if supplier and supplier.email:
                await EmailService.send_payment_proof_email(
                    to_email=supplier.email,
                    first_name=supplier.first_name or "there",
                    order_public_id=order.public_id,
                    payment_type_label=label,
                    amount=amount,
                    reference=proof.payment_reference,
                    paid_at=paid_at,
                    method=proof.method,
                    note=proof.note,
                    order_url=f"{base}/dashboard/supplier/orders/{order.public_id}",
                    attachments=attachments,
                )

        proof.notified_at = datetime.now(timezone.utc)

    @staticmethod
    async def resend(
        db: AsyncSession, admin: AdminAccount, public_id: str, proof_id: UUID
    ) -> AdminPaymentProofItem:
        order = await PaymentProofService._order(db, public_id)
        proof = await db.get(OrderPaymentProof, proof_id)
        if not proof or proof.deleted_at or proof.order_id != order.id:
            raise AppError(404, "Proof of payment not found", "not_found")
        await PaymentProofService.notify(db, order, proof)
        apply_update_audit(proof, admin.id)
        return await PaymentProofService._serialize(db, order, proof)

    @staticmethod
    async def delete(
        db: AsyncSession, admin: AdminAccount, public_id: str, proof_id: UUID
    ) -> dict:
        order = await PaymentProofService._order(db, public_id)
        proof = await db.get(OrderPaymentProof, proof_id)
        if not proof or proof.deleted_at or proof.order_id != order.id:
            raise AppError(404, "Proof of payment not found", "not_found")
        soft_delete(proof, admin.id)
        return {"ok": True}

    @staticmethod
    async def receipt_pdf(db: AsyncSession, public_id: str, proof_id: UUID):
        order = await PaymentProofService._order(db, public_id)
        proof = await db.get(OrderPaymentProof, proof_id)
        if not proof or proof.deleted_at or proof.order_id != order.id:
            raise AppError(404, "Proof of payment not found", "not_found")
        attachment = await build_payment_proof_attachment(db, order, proof)
        if not attachment:
            raise AppError(503, "Document generation is unavailable", "documents_unavailable")
        return attachment
