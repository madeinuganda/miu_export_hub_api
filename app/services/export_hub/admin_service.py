from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.shared.exceptions import AppError
from app.models.export_hub.accounts import AdminAccount, BuyerAccount, SupplierAccount
from app.models.export_hub.organizations import BuyerOrganizationMember, SupplierOrganizationMember
from app.models.export_hub.catalog import Category, Product
from app.models.shared.enums import (
    DocumentStatus,
    EscrowStatus,
    OrderStatus,
    PaymentMilestoneStatus,
    QuoteStatus,
    RfqStatus,
    SenderRole,
    VerificationStatus,
)
from app.models.export_hub.misc import AdminActionLog, BuyerRegistrationDraft, BuyerSavedSupplier, FileRecord, RegistrationDocument, SupplierRegistrationDraft
from app.models.export_hub.orders import Order, OrderActivity, OrderMilestone, OrderTracking
from app.models.export_hub.organizations import BuyerOrganization, SupplierOrganization
from app.models.export_hub.payments import PaymentEscrow, PaymentMilestone
from app.models.export_hub.rfqs import Rfq, RfqQuote
from app.services.export_hub.order_service import (
    ADMIN_PIPELINE,
    PIPELINE_BY_STAGE,
    PIPELINE_STAGE_IDS,
    OrderService,
)
from app.services.export_hub.rfq_service import RfqService
from app.services.export_hub.buyer_account_cleanup import hard_purge_buyer_account
from app.schemas.export_hub.admin import (
    AdminDealListItem,
    AdminDealListResponse,
    AdminOrderListItem,
    AdminOrderListResponse,
    AdminOrderListSummary,
    AdminRfqListItem,
    AdminRfqListResponse,
    AdminRfqListSummary,
    EscrowReleaseResponse,
    OrderMilestoneUpdateResponse,
    RelayQuoteRequest,
    RfqAssignRequest,
    BuyerAdminItem,
    BuyerAdminListResponse,
    BuyerProfileSectionItem,
    VerificationApplicationItem,
    VerificationApplicationsResponse,
    VerificationDocumentItem,
    VerifyRequest,
)
from app.utils.audit import apply_create_audit, apply_update_audit, soft_delete
from app.utils.formatting import format_quantity, format_ugx
from app.utils.pagination import paginate

# ADMIN_PIPELINE and friends now live in order_service.py so admin, supplier,
# and buyer order views all share the exact same lifecycle/milestone vocabulary.

# key, label, document_type aliases (supplier onboarding + legacy), required for verification
VERIFICATION_DOC_SPECS: list[tuple[str, str, list[str], bool]] = [
    (
        "businessRegistration",
        "Business Registration Certificate",
        ["businessRegistration", "business_license"],
        True,
    ),
    ("tin", "Tax Identification Number (TIN)", ["tin"], True),
    (
        "exportCert",
        "Export Certification",
        ["exportCert", "export_permit"],
        False,
    ),
    (
        "sitePhotos",
        "Production Site Photos",
        ["sitePhotos", "production"],
        False,
    ),
    ("contact", "Contact Information", ["contact"], False),
]


class AdminService:
    @staticmethod
    def _admin_short_name(account: AdminAccount | None) -> str | None:
        if not account:
            return None
        initial = account.last_name[0] + "." if account.last_name else ""
        return f"{account.first_name} {initial}".strip()

    @staticmethod
    async def _load_admin(db: AsyncSession, admin_id: UUID | None) -> AdminAccount | None:
        if not admin_id:
            return None
        return await db.get(AdminAccount, admin_id)

    @staticmethod
    async def _buyer_contact(db: AsyncSession, buyer_org_id: UUID) -> tuple[str, str, str]:
        org = await db.get(BuyerOrganization, buyer_org_id)
        if not org:
            return "—", "—", "—"
        member = (
            await db.execute(
                select(BuyerOrganizationMember)
                .where(
                    BuyerOrganizationMember.org_id == buyer_org_id,
                    BuyerOrganizationMember.deleted_at.is_(None),
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        name = org.procurement_contact or "—"
        if member:
            account = await db.get(BuyerAccount, member.buyer_account_id)
            if account:
                name = f"{account.first_name} {account.last_name}"
        return name, org.name, org.country

    @staticmethod
    async def _supplier_contact(db: AsyncSession, supplier_org_id: UUID) -> tuple[str, str]:
        org = await db.get(SupplierOrganization, supplier_org_id)
        if not org:
            return "—", "—"
        member = (
            await db.execute(
                select(SupplierOrganizationMember)
                .where(
                    SupplierOrganizationMember.org_id == supplier_org_id,
                    SupplierOrganizationMember.deleted_at.is_(None),
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        name = "—"
        if member:
            account = await db.get(SupplierAccount, member.supplier_account_id)
            if account:
                name = f"{account.first_name} {account.last_name[0]}." if account.last_name else account.first_name
        return name, org.name

    @staticmethod
    async def _rfq_assigned(db: AsyncSession, rfq_id: UUID) -> bool:
        log = (
            await db.execute(
                select(AdminActionLog)
                .where(
                    AdminActionLog.entity_type == "rfq",
                    AdminActionLog.entity_id == rfq_id,
                    AdminActionLog.action == "assign_rfq",
                    AdminActionLog.deleted_at.is_(None),
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        return log is not None

    @staticmethod
    def _rfq_admin_status(rfq: Rfq, routed: bool) -> str:
        if rfq.status in (RfqStatus.DECLINED, RfqStatus.CANCELLED, RfqStatus.EXPIRED):
            return "closed"
        if rfq.status == RfqStatus.ACCEPTED:
            return "closed"
        if rfq.status == RfqStatus.RESPONDED:
            return "responded"
        if routed:
            return "routed"
        return "new"

    @staticmethod
    async def notifications_summary(db: AsyncSession) -> dict:
        pending_suppliers = (
            await db.execute(
                select(func.count())
                .select_from(SupplierOrganization)
                .where(
                    SupplierOrganization.verification_status == VerificationStatus.PENDING.value,
                    SupplierOrganization.deleted_at.is_(None),
                )
            )
        ).scalar() or 0
        new_rfqs = (
            await db.execute(
                select(func.count())
                .select_from(Rfq)
                .where(Rfq.status == RfqStatus.AWAITING.value, Rfq.deleted_at.is_(None))
            )
        ).scalar() or 0
        return {"unread_count": int(pending_suppliers) + int(new_rfqs)}

    @staticmethod
    async def list_rfqs(
        db: AsyncSession,
        *,
        status: str | None = None,
        q: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> AdminRfqListResponse:
        rfqs = (
            await db.execute(select(Rfq).where(Rfq.deleted_at.is_(None)).order_by(Rfq.sent_at.desc().nullslast(), Rfq.created_at.desc()))
        ).scalars().all()

        all_items: list[AdminRfqListItem] = []
        response_hours: list[float] = []
        week_ago = datetime.now(timezone.utc) - timedelta(days=7)

        for rfq in rfqs:
            routed = await AdminService._rfq_assigned(db, rfq.id)
            admin_status = AdminService._rfq_admin_status(rfq, routed)

            buyer_name, buyer_company, buyer_country = await AdminService._buyer_contact(db, rfq.buyer_org_id)
            product = await db.get(Product, rfq.product_id)
            category = ""
            if product and product.category_id:
                cat = await db.get(Category, product.category_id)
                category = cat.label if cat else (product.subcategory or "")

            search_blob = " ".join(
                filter(
                    None,
                    [rfq.public_id, buyer_name, buyer_company, product.name if product else "", category],
                )
            ).lower()
            if q and q.strip().lower() not in search_blob:
                continue

            admin = await AdminService._load_admin(db, rfq.updated_by)
            if rfq.sent_at and rfq.sent_at >= week_ago:
                pass
            submitted = rfq.sent_at or rfq.created_at
            if admin_status == "responded" and rfq.sent_at:
                quote = (
                    await db.execute(
                        select(RfqQuote)
                        .where(RfqQuote.rfq_id == rfq.id, RfqQuote.deleted_at.is_(None))
                        .order_by(RfqQuote.sent_at.desc().nullslast())
                        .limit(1)
                    )
                ).scalar_one_or_none()
                if quote and quote.sent_at and rfq.sent_at:
                    hours = (quote.sent_at - rfq.sent_at).total_seconds() / 3600
                    response_hours.append(hours)

            action = "review_and_route" if admin_status == "new" else "view"
            pending_messages = await RfqService.pending_message_count(db, rfq.id)
            all_items.append(
                AdminRfqListItem(
                    id=rfq.id,
                    public_id=rfq.public_id,
                    buyer_name=buyer_name,
                    buyer_company=buyer_company,
                    buyer_country=buyer_country,
                    product_name=product.name if product else "",
                    category=category,
                    quantity=format_quantity(rfq.quantity, rfq.unit),
                    destination=rfq.destination_port or "",
                    submitted_at=submitted,
                    status=admin_status,
                    assigned_admin_name=AdminService._admin_short_name(admin),
                    action=action,
                    pending_message_count=pending_messages,
                )
            )

        items = all_items
        if status and status != "all":
            items = [i for i in all_items if i.status == status]

        new_count = sum(1 for i in all_items if i.status == "new")
        active_week = sum(
            1
            for rfq in rfqs
            if (rfq.sent_at or rfq.created_at) >= week_ago and rfq.status not in (RfqStatus.CANCELLED, RfqStatus.EXPIRED)
        )
        avg_hours = round(sum(response_hours) / len(response_hours), 1) if response_hours else None
        needs_review = sum(1 for i in all_items if i.pending_message_count > 0)
        paged = paginate(items, page, page_size)
        return AdminRfqListResponse(
            summary=AdminRfqListSummary(
                new_count=new_count,
                total=len(all_items),
                avg_response_hours=avg_hours,
                active_this_week=active_week,
                needs_review_count=needs_review,
            ),
            items=paged.items,
            page=paged.page,
            page_size=paged.page_size,
            total=paged.total,
            pages=paged.pages,
        )

    @staticmethod
    async def get_rfq_detail(db: AsyncSession, public_id: str) -> dict:
        rfq = (
            await db.execute(select(Rfq).where(Rfq.public_id == public_id, Rfq.deleted_at.is_(None)))
        ).scalar_one_or_none()
        if not rfq:
            raise AppError(404, "RFQ not found", "not_found")

        buyer_name, buyer_company, buyer_country = await AdminService._buyer_contact(db, rfq.buyer_org_id)
        product = await db.get(Product, rfq.product_id)
        routed = await AdminService._rfq_assigned(db, rfq.id)
        admin_status = AdminService._rfq_admin_status(rfq, routed)

        suggested = []
        if product and product.category_id:
            suppliers = (
                await db.execute(
                    select(SupplierOrganization)
                    .join(Product, Product.supplier_org_id == SupplierOrganization.id)
                    .where(
                        Product.category_id == product.category_id,
                        SupplierOrganization.verification_status == VerificationStatus.APPROVED.value,
                        SupplierOrganization.deleted_at.is_(None),
                        Product.deleted_at.is_(None),
                    )
                    .distinct()
                    .limit(8)
                )
            ).scalars().all()
            suggested = [{"org_id": str(s.id), "name": s.name, "region": s.region or s.district} for s in suppliers]

        quotes = (
            await db.execute(select(RfqQuote).where(RfqQuote.rfq_id == rfq.id, RfqQuote.deleted_at.is_(None)))
        ).scalars().all()
        messages = await RfqService.list_messages_for_admin(db, rfq.id)
        pending_message_count = sum(1 for m in messages if m["reviewStatus"] == "pending")
        assign_logs = (
            await db.execute(
                select(AdminActionLog)
                .where(
                    AdminActionLog.entity_type == "rfq",
                    AdminActionLog.entity_id == rfq.id,
                    AdminActionLog.action == "assign_rfq",
                    AdminActionLog.deleted_at.is_(None),
                )
                .order_by(AdminActionLog.created_at.desc())
            )
        ).scalars().all()
        history = []
        for log in assign_logs:
            admin = await AdminService._load_admin(db, log.admin_account_id)
            history.append(
                {
                    "at": log.created_at.isoformat(),
                    "admin_name": AdminService._admin_short_name(admin),
                    "note": (log.metadata_ or {}).get("note"),
                    "supplier_org_ids": (log.metadata_ or {}).get("supplier_org_ids", []),
                }
            )

        admin = await AdminService._load_admin(db, rfq.updated_by)
        return {
            "id": str(rfq.id),
            "public_id": rfq.public_id,
            "rfq_public_id": rfq.public_id,
            "status": admin_status,
            "buyer": {
                "name": buyer_name,
                "company": buyer_company,
                "country": buyer_country,
                "message": rfq.message,
            },
            "product": {
                "name": product.name if product else "",
                "quantity": format_quantity(rfq.quantity, rfq.unit),
                "destination": rfq.destination_port,
                "incoterm": rfq.incoterm,
                "target_price": format_ugx(rfq.target_price_amount or 0, rfq.unit) if rfq.target_price_amount else None,
            },
            "suggested_suppliers": suggested,
            "quotes": [
                {
                    "id": str(q.id),
                    "supplier_org_id": str(q.supplier_org_id),
                    "unit_price": float(q.unit_price),
                    "currency": q.currency,
                    "status": q.status.value,
                    "notes": q.notes,
                }
                for q in quotes
            ],
            "messages": messages,
            "pending_message_count": pending_message_count,
            "assignment_history": history,
            "assigned_admin_name": AdminService._admin_short_name(admin),
            "updated_at": rfq.updated_at.isoformat(),
        }

    @staticmethod
    async def assign_rfq(db: AsyncSession, admin: AdminAccount, public_id: str, data: RfqAssignRequest) -> dict:
        rfq = (
            await db.execute(select(Rfq).where(Rfq.public_id == public_id, Rfq.deleted_at.is_(None)))
        ).scalar_one_or_none()
        if not rfq:
            raise AppError(404, "RFQ not found", "not_found")
        if rfq.status not in (RfqStatus.AWAITING, RfqStatus.RESPONDED):
            raise AppError(400, "RFQ cannot be routed in its current status", "invalid_status")

        for org_id in data.supplier_org_ids:
            org = await db.get(SupplierOrganization, org_id)
            if not org or org.deleted_at:
                raise AppError(404, f"Supplier {org_id} not found", "not_found")

        if data.supplier_org_ids:
            rfq.supplier_org_id = data.supplier_org_ids[0]
        apply_update_audit(rfq, admin.id)

        log = AdminActionLog(
            admin_account_id=admin.id,
            action="assign_rfq",
            entity_type="rfq",
            entity_id=rfq.id,
            metadata_={"supplier_org_ids": [str(x) for x in data.supplier_org_ids], "note": data.note},
        )
        apply_create_audit(log, admin.id)
        db.add(log)
        return {"ok": True, "public_id": rfq.public_id, "status": "routed"}

    @staticmethod
    async def _deal_status(db: AsyncSession, rfq: Rfq, quote: RfqQuote | None) -> str:
        order = (
            await db.execute(select(Order).where(Order.rfq_id == rfq.id, Order.deleted_at.is_(None)).limit(1))
        ).scalar_one_or_none()
        if order:
            if order.status in (OrderStatus.DELIVERED, OrderStatus.FULFILLED):
                return "completed"
            return "order_created"
        if rfq.status == RfqStatus.ACCEPTED or (quote and quote.status == QuoteStatus.ACCEPTED):
            return "accepted"
        if quote and quote.status == QuoteStatus.SENT:
            return "quote_sent"
        return "active"

    @staticmethod
    def _deal_public_id(rfq: Rfq) -> str:
        suffix = rfq.public_id.replace("RFQ-", "", 1) if rfq.public_id.startswith("RFQ-") else rfq.public_id
        return f"DEAL-{suffix}"

    @staticmethod
    async def list_deals(
        db: AsyncSession,
        *,
        status: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> AdminDealListResponse:
        rfqs = (
            await db.execute(
                select(Rfq)
                .where(
                    Rfq.deleted_at.is_(None),
                    Rfq.status.in_((RfqStatus.AWAITING.value, RfqStatus.RESPONDED.value, RfqStatus.ACCEPTED.value)),
                )
                .order_by(Rfq.updated_at.desc())
            )
        ).scalars().all()

        items: list[AdminDealListItem] = []
        for rfq in rfqs:
            quote = (
                await db.execute(
                    select(RfqQuote)
                    .where(RfqQuote.rfq_id == rfq.id, RfqQuote.deleted_at.is_(None))
                    .order_by(RfqQuote.updated_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if not quote and rfq.status == RfqStatus.AWAITING:
                continue

            deal_status = await AdminService._deal_status(db, rfq, quote)
            if status and status != "all" and deal_status != status:
                continue

            buyer_name, buyer_company, _ = await AdminService._buyer_contact(db, rfq.buyer_org_id)
            supplier_name, supplier_company = await AdminService._supplier_contact(db, rfq.supplier_org_id)
            product = await db.get(Product, rfq.product_id)
            value = int((quote.unit_price * rfq.quantity) if quote else (product.price_amount or 0) * rfq.quantity if product else 0)
            admin = await AdminService._load_admin(db, rfq.updated_by)
            last_at = quote.sent_at if quote and quote.sent_at else rfq.updated_at
            pending_messages = await RfqService.pending_message_count(db, rfq.id)

            items.append(
                AdminDealListItem(
                    id=rfq.id,
                    public_id=AdminService._deal_public_id(rfq),
                    buyer_name=buyer_name,
                    buyer_company=buyer_company,
                    supplier_name=supplier_name,
                    supplier_company=supplier_company,
                    product=product.name if product else "",
                    value_ugx=value,
                    value_display=format_ugx(value),
                    status=deal_status,
                    last_activity_at=last_at,
                    assigned_admin_name=AdminService._admin_short_name(admin),
                    pending_message_count=pending_messages,
                )
            )

        active = sum(1 for i in items if i.status in ("active", "quote_sent"))
        needs_review = sum(1 for i in items if i.pending_message_count > 0)
        paged = paginate(items, page, page_size)
        return AdminDealListResponse(
            active_deals_count=active,
            needs_review_count=needs_review,
            items=paged.items,
            page=paged.page,
            page_size=paged.page_size,
            total=paged.total,
            pages=paged.pages,
        )

    @staticmethod
    async def get_deal_detail(db: AsyncSession, public_id: str) -> dict:
        suffix = public_id.replace("DEAL-", "", 1) if public_id.startswith("DEAL-") else public_id
        rfq_public = public_id if public_id.startswith("RFQ-") else f"RFQ-{suffix}"
        rfq = (
            await db.execute(select(Rfq).where(Rfq.public_id == rfq_public, Rfq.deleted_at.is_(None)))
        ).scalar_one_or_none()
        if not rfq:
            raise AppError(404, "Deal not found", "not_found")

        detail = await AdminService.get_rfq_detail(db, rfq.public_id)
        detail["public_id"] = AdminService._deal_public_id(rfq)
        detail["deal_status"] = await AdminService._deal_status(
            db,
            rfq,
            (
                await db.execute(
                    select(RfqQuote).where(RfqQuote.rfq_id == rfq.id, RfqQuote.deleted_at.is_(None)).limit(1)
                )
            ).scalar_one_or_none(),
        )
        return detail

    @staticmethod
    async def relay_quote(db: AsyncSession, admin: AdminAccount, public_id: str, data: RelayQuoteRequest) -> dict:
        rfq = (
            await db.execute(select(Rfq).where(Rfq.public_id == public_id, Rfq.deleted_at.is_(None)))
        ).scalar_one_or_none()
        if not rfq:
            raise AppError(404, "RFQ not found", "not_found")

        if data.quote_id:
            quote = await db.get(RfqQuote, data.quote_id)
        else:
            quote = (
                await db.execute(
                    select(RfqQuote)
                    .where(RfqQuote.rfq_id == rfq.id, RfqQuote.deleted_at.is_(None))
                    .order_by(RfqQuote.created_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()

        if not quote or quote.rfq_id != rfq.id:
            raise AppError(404, "Quote not found", "not_found")

        quote.status = QuoteStatus.SENT
        quote.sent_at = datetime.now(timezone.utc)
        apply_update_audit(quote, admin.id)
        rfq.status = RfqStatus.RESPONDED
        apply_update_audit(rfq, admin.id)

        if data.message:
            await RfqService.add_message(db, rfq.id, SenderRole.ADMIN, data.message, admin.id)

        log = AdminActionLog(
            admin_account_id=admin.id,
            action="relay_quote",
            entity_type="rfq",
            entity_id=rfq.id,
            metadata_={"quote_id": str(quote.id), "message": data.message},
        )
        apply_create_audit(log, admin.id)
        db.add(log)
        return {"ok": True, "public_id": rfq.public_id, "deal_id": AdminService._deal_public_id(rfq)}

    @staticmethod
    async def _resolve_rfq_by_public_id(db: AsyncSession, public_id: str) -> Rfq:
        """Accepts either an RFQ public id (RFQ-2026-001) or a Deal public id
        (DEAL-2026-001, derived from the same RFQ) and resolves the Rfq row."""
        suffix = public_id.replace("DEAL-", "", 1) if public_id.startswith("DEAL-") else public_id
        rfq_public = public_id if public_id.startswith("RFQ-") else f"RFQ-{suffix}"
        rfq = (
            await db.execute(select(Rfq).where(Rfq.public_id == rfq_public, Rfq.deleted_at.is_(None)))
        ).scalar_one_or_none()
        if not rfq:
            raise AppError(404, "RFQ not found", "not_found")
        return rfq

    @staticmethod
    async def send_relay_message(db: AsyncSession, admin: AdminAccount, public_id: str, body: str) -> dict:
        """Admin posts a message directly into the thread; it's visible to
        both parties immediately (no review needed since admin authored it)."""
        rfq = await AdminService._resolve_rfq_by_public_id(db, public_id)
        msg = await RfqService.add_message(db, rfq.id, SenderRole.ADMIN, body, admin.id)
        return RfqService._serialize_message(msg, admin_view=True)

    @staticmethod
    async def route_message(db: AsyncSession, admin: AdminAccount, public_id: str, message_id: UUID, note: str | None) -> dict:
        rfq = await AdminService._resolve_rfq_by_public_id(db, public_id)
        msg = await RfqService.route_message(db, admin.id, rfq.id, message_id, note)
        return RfqService._serialize_message(msg, admin_view=True)

    @staticmethod
    async def revert_message(db: AsyncSession, admin: AdminAccount, public_id: str, message_id: UUID, remarks: str) -> dict:
        rfq = await AdminService._resolve_rfq_by_public_id(db, public_id)
        msg = await RfqService.revert_message(db, admin.id, rfq.id, message_id, remarks)
        return RfqService._serialize_message(msg, admin_view=True)

    @staticmethod
    async def list_thread_messages(db: AsyncSession, public_id: str) -> dict:
        rfq = await AdminService._resolve_rfq_by_public_id(db, public_id)
        return {"rfqPublicId": rfq.public_id, "messages": await RfqService.list_messages_for_admin(db, rfq.id)}

    @staticmethod
    def pipeline_stages() -> list[dict]:
        return OrderService.pipeline_stages()

    @staticmethod
    def _order_pipeline_index(order: Order) -> int:
        return OrderService.order_pipeline_index(order)

    @staticmethod
    async def _sync_admin_pipeline_milestones(
        db: AsyncSession,
        order: Order,
        target_index: int,
        admin_id: UUID,
    ) -> list[OrderMilestone]:
        return await OrderService.sync_pipeline_milestones(db, order, target_index, admin_id)

    @staticmethod
    def _pipeline_steps_for_index(pipeline_index: int) -> list[dict]:
        steps = []
        for i, (stage_id, label, _) in enumerate(ADMIN_PIPELINE):
            state = "upcoming"
            if i < pipeline_index:
                state = "complete"
            elif i == pipeline_index:
                state = "current"
            steps.append({"id": stage_id, "label": label, "state": state})
        return steps

    @staticmethod
    def _payment_status_label(escrow: PaymentEscrow | None) -> str:
        if not escrow:
            return "in_escrow"
        if escrow.status == EscrowStatus.BALANCE_RELEASED:
            return "released"
        return "in_escrow"

    @staticmethod
    async def _serialize_order_item(db: AsyncSession, order: Order) -> AdminOrderListItem:
        product = await db.get(Product, order.product_id)
        buyer_name, _, _ = await AdminService._buyer_contact(db, order.buyer_org_id)
        _, supplier_name = await AdminService._supplier_contact(db, order.supplier_org_id)
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
        admin = await AdminService._load_admin(db, order.updated_by)
        pipeline_index = AdminService._order_pipeline_index(order)
        stage = PIPELINE_STAGE_IDS[pipeline_index]

        product_label = product.name if product else ""
        if product:
            product_label = f"{product.name} ({format_quantity(order.quantity, order.unit)})"

        return AdminOrderListItem(
            id=order.id,
            public_id=order.public_id,
            product=product_label,
            buyer_name=buyer_name,
            supplier_name=supplier_name,
            value_display=format_ugx(order.total_value_amount),
            order_date=order.created_at.date().isoformat(),
            assigned_admin_name=AdminService._admin_short_name(admin),
            pipeline_stage=stage,
            pipeline_index=pipeline_index,
            payment_status=AdminService._payment_status_label(escrow),
            carrier=tracking.carrier if tracking else None,
            tracking_number=tracking.tracking_number if tracking else None,
        )

    @staticmethod
    async def list_orders(
        db: AsyncSession,
        *,
        stage: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> AdminOrderListResponse:
        orders = (
            await db.execute(select(Order).where(Order.deleted_at.is_(None)).order_by(Order.created_at.desc()))
        ).scalars().all()

        items: list[AdminOrderListItem] = []
        total_value = Decimal(0)
        for order in orders:
            item = await AdminService._serialize_order_item(db, order)
            if stage and stage != "all" and item.pipeline_stage != stage:
                continue
            items.append(item)
            total_value += order.total_value_amount

        paged = paginate(items, page, page_size)
        return AdminOrderListResponse(
            summary=AdminOrderListSummary(
                total_value_ugx=int(total_value),
                total_value_display=format_ugx(total_value),
            ),
            items=paged.items,
            page=paged.page,
            page_size=paged.page_size,
            total=paged.total,
            pages=paged.pages,
        )

    @staticmethod
    async def get_order_detail(db: AsyncSession, public_id: str) -> dict:
        order = (
            await db.execute(select(Order).where(Order.public_id == public_id, Order.deleted_at.is_(None)))
        ).scalar_one_or_none()
        if not order:
            raise AppError(404, "Order not found", "not_found")

        listing = await AdminService._serialize_order_item(db, order)
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

        pipeline_index = listing.pipeline_index
        steps = AdminService._pipeline_steps_for_index(pipeline_index)
        can_advance = pipeline_index < len(ADMIN_PIPELINE) - 1
        next_label = ADMIN_PIPELINE[pipeline_index + 1][1] if can_advance else None

        return {
            **listing.model_dump(),
            "pipeline_steps": steps,
            "pipeline_stages": AdminService.pipeline_stages(),
            "can_advance": can_advance,
            "next_stage": ADMIN_PIPELINE[pipeline_index + 1][0] if can_advance else None,
            "next_stage_label": next_label,
            "escrow": {
                "total": format_ugx(escrow.total_amount) if escrow else None,
                "upfront": format_ugx(escrow.upfront_amount) if escrow else None,
                "balance": format_ugx(escrow.balance_amount) if escrow else None,
                "status": escrow.status.value if escrow else None,
            },
            "tracking": {
                "carrier": tracking.carrier if tracking else None,
                "tracking_number": tracking.tracking_number if tracking else None,
                "eta": tracking.eta_date.isoformat() if tracking and tracking.eta_date else None,
            },
            "updated_at": order.updated_at.isoformat(),
        }

    @staticmethod
    async def _apply_order_stage(
        db: AsyncSession,
        admin: AdminAccount,
        order: Order,
        target_index: int,
        *,
        carrier: str | None = None,
        tracking_number: str | None = None,
    ) -> OrderMilestoneUpdateResponse:
        _, target_label, target_status = ADMIN_PIPELINE[target_index]
        order.status = target_status
        apply_update_audit(order, admin.id)
        await AdminService._sync_admin_pipeline_milestones(db, order, target_index, admin.id)

        if target_index >= PIPELINE_BY_STAGE["shipped"][0] and (carrier or tracking_number):
            tracking = (
                await db.execute(
                    select(OrderTracking).where(
                        OrderTracking.order_id == order.id,
                        OrderTracking.deleted_at.is_(None),
                    ).limit(1)
                )
            ).scalar_one_or_none()
            if not tracking:
                tracking = OrderTracking(order_id=order.id, created_by=admin.id, updated_by=admin.id)
                db.add(tracking)
            if carrier:
                tracking.carrier = carrier
            if tracking_number:
                tracking.tracking_number = tracking_number
            apply_update_audit(tracking, admin.id)

        db.add(
            OrderActivity(
                order_id=order.id,
                occurred_at=datetime.now(timezone.utc),
                description=f"Order advanced to {target_label}.",
                created_by=admin.id,
                updated_by=admin.id,
            )
        )
        log = AdminActionLog(
            admin_account_id=admin.id,
            action="advance_order",
            entity_type="order",
            entity_id=order.id,
            metadata_={"pipeline_stage": ADMIN_PIPELINE[target_index][0], "pipeline_index": target_index},
        )
        apply_create_audit(log, admin.id)
        db.add(log)

        updated = await AdminService._serialize_order_item(db, order)
        can_advance = target_index < len(ADMIN_PIPELINE) - 1
        next_stage = ADMIN_PIPELINE[target_index + 1][0] if can_advance else None
        next_label = ADMIN_PIPELINE[target_index + 1][1] if can_advance else None

        return OrderMilestoneUpdateResponse(
            order=updated,
            pipeline_stage=ADMIN_PIPELINE[target_index][0],
            pipeline_index=target_index,
            next_stage=next_stage,
            next_stage_label=next_label,
            can_advance=can_advance,
        )

    @staticmethod
    async def update_order_milestones(
        db: AsyncSession,
        admin: AdminAccount,
        public_id: str,
        *,
        pipeline_stage: str,
        carrier: str | None,
        tracking_number: str | None,
        admin_override: bool,
    ) -> OrderMilestoneUpdateResponse:
        order = (
            await db.execute(select(Order).where(Order.public_id == public_id, Order.deleted_at.is_(None)))
        ).scalar_one_or_none()
        if not order:
            raise AppError(404, "Order not found", "not_found")
        if pipeline_stage not in PIPELINE_BY_STAGE:
            raise AppError(
                422,
                f"Invalid pipeline_stage. Use one of: {', '.join(PIPELINE_STAGE_IDS)}",
                "validation_error",
            )

        current_index = AdminService._order_pipeline_index(order)
        target_index, _, _ = PIPELINE_BY_STAGE[pipeline_stage]
        if not admin_override and target_index != current_index + 1 and target_index != current_index:
            next_id = PIPELINE_STAGE_IDS[current_index + 1] if current_index < len(ADMIN_PIPELINE) - 1 else None
            raise AppError(
                400,
                f"Can only advance to the next stage ({next_id}) unless admin_override is true",
                "invalid_transition",
            )

        return await AdminService._apply_order_stage(
            db,
            admin,
            order,
            target_index,
            carrier=carrier,
            tracking_number=tracking_number,
        )

    @staticmethod
    async def advance_order(
        db: AsyncSession,
        admin: AdminAccount,
        public_id: str,
        *,
        carrier: str | None = None,
        tracking_number: str | None = None,
    ) -> OrderMilestoneUpdateResponse:
        """Advance order by one step: Confirmed → … → Fulfilled."""
        order = (
            await db.execute(select(Order).where(Order.public_id == public_id, Order.deleted_at.is_(None)))
        ).scalar_one_or_none()
        if not order:
            raise AppError(404, "Order not found", "not_found")

        current_index = AdminService._order_pipeline_index(order)
        if current_index >= len(ADMIN_PIPELINE) - 1:
            raise AppError(400, "Order is already at Fulfilled", "already_fulfilled")

        target_index = current_index + 1
        ship_carrier = carrier
        ship_tracking = tracking_number
        if target_index == PIPELINE_BY_STAGE["shipped"][0] and not ship_carrier:
            ship_carrier = "DHL Express"

        return await AdminService._apply_order_stage(
            db,
            admin,
            order,
            target_index,
            carrier=ship_carrier,
            tracking_number=ship_tracking,
        )

    @staticmethod
    async def release_escrow(db: AsyncSession, admin: AdminAccount, public_id: str) -> EscrowReleaseResponse:
        order = (
            await db.execute(select(Order).where(Order.public_id == public_id, Order.deleted_at.is_(None)))
        ).scalar_one_or_none()
        if not order:
            raise AppError(404, "Order not found", "not_found")
        escrow = (
            await db.execute(
                select(PaymentEscrow).where(PaymentEscrow.order_id == order.id, PaymentEscrow.deleted_at.is_(None)).limit(1)
            )
        ).scalar_one_or_none()
        if not escrow:
            raise AppError(404, "Escrow not found", "not_found")
        if escrow.status == EscrowStatus.BALANCE_RELEASED:
            return EscrowReleaseResponse(public_id=order.public_id, payment_status="released", released=False)

        escrow.status = EscrowStatus.BALANCE_RELEASED
        apply_update_audit(escrow, admin.id)
        apply_update_audit(order, admin.id)

        balance_milestone = (
            await db.execute(
                select(PaymentMilestone).where(
                    PaymentMilestone.escrow_id == escrow.id,
                    PaymentMilestone.milestone_type == "balance",
                    PaymentMilestone.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if balance_milestone:
            balance_milestone.status = PaymentMilestoneStatus.RELEASED
            balance_milestone.released_at = datetime.now(timezone.utc)
            apply_update_audit(balance_milestone, admin.id)
        else:
            db.add(
                PaymentMilestone(
                    escrow_id=escrow.id,
                    milestone_type="balance",
                    amount=escrow.balance_amount,
                    status=PaymentMilestoneStatus.RELEASED,
                    released_at=datetime.now(timezone.utc),
                    created_by=admin.id,
                    updated_by=admin.id,
                )
            )

        log = AdminActionLog(
            admin_account_id=admin.id,
            action="release_escrow",
            entity_type="order",
            entity_id=order.id,
            metadata_={},
        )
        apply_create_audit(log, admin.id)
        db.add(log)
        return EscrowReleaseResponse(public_id=order.public_id, payment_status="released", released=True)

    @staticmethod
    async def _latest_info_request_log(db: AsyncSession, org_id: UUID):
        return (
            await db.execute(
                select(AdminActionLog)
                .where(
                    AdminActionLog.entity_type == "supplier_org",
                    AdminActionLog.entity_id == org_id,
                    AdminActionLog.action == "request_verification_info",
                    AdminActionLog.deleted_at.is_(None),
                )
                .order_by(AdminActionLog.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

    @staticmethod
    async def _info_requested(db: AsyncSession, org_id: UUID) -> bool:
        return (await AdminService._latest_info_request_log(db, org_id)) is not None

    @staticmethod
    def _missing_items_from_documents(docs: list[VerificationDocumentItem]) -> list[str]:
        return [
            doc.label
            for doc in docs
            if doc.status in ("missing", "flagged") and doc.key != "contact"
        ]

    @staticmethod
    async def effective_verification_status(db: AsyncSession, org: SupplierOrganization) -> str:
        """UI status: action_required when admin requested info (without DB enum value)."""
        log = await AdminService._latest_info_request_log(db, org.id)
        if not log:
            return org.verification_status.value
        if org.verification_status == VerificationStatus.PENDING:
            return "action_required"
        if org.verification_status == VerificationStatus.APPROVED and not org.storefront_published:
            return "action_required"
        return org.verification_status.value

    @staticmethod
    async def get_action_required_summary(db: AsyncSession, org_id: UUID) -> dict:
        log = await AdminService._latest_info_request_log(db, org_id)
        docs = await AdminService._verification_documents(db, org_id)
        missing = AdminService._missing_items_from_documents(docs)
        message = None
        if log and isinstance(log.metadata_, dict):
            meta = log.metadata_
            if meta.get("missing_items"):
                missing = list(meta["missing_items"])
            message = meta.get("message")
        if not message:
            message = (
                "MIU admin has requested updates to your application. "
                "Please provide the missing information below."
            )
        return {"message": message, "missingItems": missing}

    @staticmethod
    def _draft_documents_payload(db_payload: dict | None) -> dict:
        if not db_payload:
            return {}
        documents = db_payload.get("documents")
        return documents if isinstance(documents, dict) else {}

    @staticmethod
    def _pick_registration_doc(
        reg_by_type: dict[str, RegistrationDocument],
        aliases: list[str],
    ) -> RegistrationDocument | None:
        for alias in aliases:
            reg = reg_by_type.get(alias)
            if reg:
                return reg
        return None

    @staticmethod
    def _pick_draft_doc_entry(payload_docs: dict, aliases: list[str], key: str) -> dict | None:
        for alias in aliases + [key]:
            entry = payload_docs.get(alias)
            if entry is True:
                return {"uploaded": True}
            if isinstance(entry, dict):
                return entry
        return None

    @staticmethod
    def _parse_file_uuid(value: object) -> UUID | None:
        if value is None:
            return None
        try:
            return UUID(str(value))
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _file_id_from_draft_entry(entry: dict | None) -> UUID | None:
        if not entry:
            return None
        return AdminService._parse_file_uuid(
            entry.get("fileId") or entry.get("file_id") or entry.get("id")
        )

    @staticmethod
    async def _org_draft_documents(db: AsyncSession, org_id: UUID) -> dict:
        """Merge document entries from all active member registration drafts."""
        account_ids = (
            await db.execute(
                select(SupplierOrganizationMember.supplier_account_id).where(
                    SupplierOrganizationMember.org_id == org_id,
                    SupplierOrganizationMember.deleted_at.is_(None),
                )
            )
        ).scalars().all()

        merged: dict = {}
        for account_id in account_ids:
            draft = (
                await db.execute(
                    select(SupplierRegistrationDraft).where(
                        SupplierRegistrationDraft.supplier_account_id == account_id,
                        SupplierRegistrationDraft.deleted_at.is_(None),
                    )
                )
            ).scalar_one_or_none()
            if not draft or not draft.payload:
                continue
            for doc_key, entry in AdminService._draft_documents_payload(draft.payload).items():
                if entry is True:
                    merged[doc_key] = {"uploaded": True}
                elif isinstance(entry, dict) and (
                    entry.get("fileId")
                    or entry.get("file_id")
                    or entry.get("uploaded")
                    or entry.get("filename")
                ):
                    merged[doc_key] = entry
        return merged

    @staticmethod
    async def _verification_documents(db: AsyncSession, org_id: UUID) -> list[VerificationDocumentItem]:
        docs: list[VerificationDocumentItem] = []
        reg_docs = (
            await db.execute(
                select(RegistrationDocument).where(
                    RegistrationDocument.org_id == org_id, RegistrationDocument.deleted_at.is_(None)
                )
            )
        ).scalars().all()
        reg_by_type = {d.document_type: d for d in reg_docs}
        payload_docs = await AdminService._org_draft_documents(db, org_id)

        member = (
            await db.execute(
                select(SupplierOrganizationMember).where(
                    SupplierOrganizationMember.org_id == org_id,
                    SupplierOrganizationMember.deleted_at.is_(None),
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        account = None
        if member:
            account = await db.get(SupplierAccount, member.supplier_account_id)

        for key, label, aliases, required in VERIFICATION_DOC_SPECS:
            if key == "contact":
                contact_ok = bool(
                    account
                    and account.email
                    and account.phone
                    and (account.first_name or account.last_name)
                )
                docs.append(
                    VerificationDocumentItem(
                        key=key,
                        label=label,
                        status="verified" if contact_ok else "flagged",
                        required=required,
                        has_file=False,
                    )
                )
                continue

            reg = AdminService._pick_registration_doc(reg_by_type, aliases)
            draft_entry = AdminService._pick_draft_doc_entry(payload_docs, aliases, key)

            file_id: UUID | None = reg.file_id if reg and reg.file_id else None
            filename: str | None = None
            if draft_entry:
                filename = draft_entry.get("filename")
                if not file_id:
                    file_id = AdminService._file_id_from_draft_entry(draft_entry)

            if not file_id:
                for alias in aliases + [key]:
                    candidate = reg_by_type.get(alias)
                    if candidate and candidate.file_id:
                        file_id = candidate.file_id
                        reg = candidate
                        break

            record = await db.get(FileRecord, file_id) if file_id else None
            if record and record.deleted_at:
                record = None

            if not file_id or not record:
                status = "missing"
                mime_type = None
                has_file = False
            elif reg and reg.status == DocumentStatus.APPROVED:
                status = "verified"
                mime_type = record.mime_type
                has_file = True
            elif reg and reg.status == DocumentStatus.REJECTED:
                status = "flagged"
                mime_type = record.mime_type
                has_file = True
            else:
                status = "flagged"
                mime_type = record.mime_type
                has_file = True

            docs.append(
                VerificationDocumentItem(
                    key=key,
                    label=label,
                    status=status,
                    required=required,
                    has_file=has_file,
                    file_id=file_id if has_file else None,
                    filename=filename or (Path(record.storage_key).name if record else None),
                    mime_type=mime_type,
                    file_url=None,
                )
            )
        return docs

    @staticmethod
    async def _serialize_verification_app(db: AsyncSession, org: SupplierOrganization) -> VerificationApplicationItem:
        member = (
            await db.execute(
                select(SupplierOrganizationMember)
                .where(
                    SupplierOrganizationMember.org_id == org.id,
                    SupplierOrganizationMember.deleted_at.is_(None),
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        contact_name = "—"
        email = "—"
        if member:
            account = await db.get(SupplierAccount, member.supplier_account_id)
            if account:
                contact_name = f"{account.first_name} {account.last_name}"
                email = account.email

        submitted = org.updated_at if org.verification_status == VerificationStatus.PENDING else org.approved_at
        hours = 0
        if submitted:
            hours = int((datetime.now(timezone.utc) - submitted).total_seconds() / 3600)

        review_status = await AdminService.effective_verification_status(db, org)
        if review_status not in ("pending", "approved", "rejected", "action_required", "suspended"):
            review_status = "pending"

        location = ", ".join(filter(None, [org.district, org.region, "Uganda"]))
        documents = await AdminService._verification_documents(db, org.id)
        info_log = await AdminService._latest_info_request_log(db, org.id)
        admin_message = None
        missing_items: list[str] = []
        meta = info_log.metadata_ if info_log and isinstance(info_log.metadata_, dict) else {}
        if meta:
            admin_message = meta.get("message")
            stored = meta.get("missing_items")
            if stored:
                missing_items = list(stored)
        if not missing_items and review_status == "action_required":
            missing_items = AdminService._missing_items_from_documents(documents)

        return VerificationApplicationItem(
            id=org.id,
            org_id=org.id,
            company_name=org.name,
            industry=org.category or org.business_type or "—",
            location=location,
            contact_name=contact_name,
            email=email,
            submitted_at=submitted,
            hours_elapsed=hours,
            status=review_status,
            info_requested=info_log is not None or review_status == "action_required",
            admin_message=admin_message,
            missing_items=missing_items,
            documents=documents,
        )

    @staticmethod
    async def list_verification_applications(
        db: AsyncSession,
        *,
        status: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> VerificationApplicationsResponse:
        orgs = (
            await db.execute(
                select(SupplierOrganization).where(
                    SupplierOrganization.deleted_at.is_(None),
                    SupplierOrganization.verification_status.in_(
                        (
                            VerificationStatus.PENDING.value,
                            VerificationStatus.APPROVED.value,
                            VerificationStatus.REJECTED.value,
                            VerificationStatus.SUSPENDED.value,
                        )
                    ),
                )
                .order_by(SupplierOrganization.updated_at.desc())
            )
        ).scalars().all()

        pending: list[VerificationApplicationItem] = []
        processed: list[VerificationApplicationItem] = []
        for org in orgs:
            app = await AdminService._serialize_verification_app(db, org)
            if status == "pending" and app.status not in ("pending", "action_required"):
                continue
            if status == "approved" and app.status != "approved":
                continue
            if status == "rejected" and app.status != "rejected":
                continue
            if status == "processed" and app.status in ("pending", "action_required"):
                continue
            if app.status in ("pending", "action_required"):
                pending.append(app)
            else:
                processed.append(app)

        combined = pending + processed
        paged = paginate(combined, page, page_size)
        summary = {
            "pending": len([a for a in combined if a.status in ("pending", "action_required")]),
            "approved": len([a for a in combined if a.status == "approved"]),
            "rejected": len([a for a in combined if a.status == "rejected"]),
        }
        pending_slice = [a for a in paged.items if a.status in ("pending", "action_required")]
        processed_slice = [a for a in paged.items if a.status not in ("pending", "action_required")]
        return VerificationApplicationsResponse(
            summary=summary,
            pending=pending_slice,
            processed=processed_slice,
            page=paged.page,
            page_size=paged.page_size,
            total=paged.total,
            pages=paged.pages,
        )

    @staticmethod
    async def get_verification_application(db: AsyncSession, application_id: UUID) -> VerificationApplicationItem:
        org = await db.get(SupplierOrganization, application_id)
        if not org or org.deleted_at:
            raise AppError(404, "Application not found", "not_found")
        return await AdminService._serialize_verification_app(db, org)

    @staticmethod
    async def verify_supplier(db: AsyncSession, admin: AdminAccount, org_id: UUID, data: VerifyRequest) -> dict:
        org = await db.get(SupplierOrganization, org_id)
        if not org or org.deleted_at:
            raise AppError(404, "Supplier not found", "not_found")
        org.verification_status = VerificationStatus.APPROVED if data.approved else VerificationStatus.REJECTED
        if data.approved:
            org.approved_at = datetime.now(timezone.utc)
            org.storefront_published = True
        apply_update_audit(org, admin.id)
        log = AdminActionLog(
            admin_account_id=admin.id,
            action="verify_supplier",
            entity_type="supplier_org",
            entity_id=org_id,
            metadata_={"approved": data.approved, "reason": data.reason},
        )
        apply_create_audit(log, admin.id)
        db.add(log)
        return {"status": org.verification_status.value}

    @staticmethod
    async def request_verification_info(
        db: AsyncSession, admin: AdminAccount, application_id: UUID, message: str | None
    ) -> dict:
        org = await db.get(SupplierOrganization, application_id)
        if not org or org.deleted_at:
            raise AppError(404, "Application not found", "not_found")
        if org.verification_status not in (
            VerificationStatus.PENDING,
            VerificationStatus.APPROVED,
        ):
            raise AppError(400, "Cannot request information for this application", "invalid_status")

        documents = await AdminService._verification_documents(db, org.id)
        missing_items = AdminService._missing_items_from_documents(documents)
        if not missing_items:
            missing_items = ["Additional documentation or clarification"]

        org.storefront_published = False
        apply_update_audit(org, admin.id)

        default_message = (
            "Please update your application with the missing or flagged items listed below."
        )
        log = AdminActionLog(
            admin_account_id=admin.id,
            action="request_verification_info",
            entity_type="supplier_org",
            entity_id=org.id,
            metadata_={
                "message": message or default_message,
                "missing_items": missing_items,
            },
        )
        apply_create_audit(log, admin.id)
        db.add(log)
        return {
            "ok": True,
            "info_requested": True,
            "status": org.verification_status.value,
            "missing_items": missing_items,
        }

    @staticmethod
    async def suspend_supplier(
        db: AsyncSession, admin: AdminAccount, application_id: UUID, reason: str | None
    ) -> dict:
        org = await db.get(SupplierOrganization, application_id)
        if not org or org.deleted_at:
            raise AppError(404, "Application not found", "not_found")
        if org.verification_status != VerificationStatus.APPROVED:
            raise AppError(400, "Only approved suppliers can be suspended", "invalid_status")

        org.verification_status = VerificationStatus.SUSPENDED
        org.storefront_published = False
        apply_update_audit(org, admin.id)
        log = AdminActionLog(
            admin_account_id=admin.id,
            action="suspend_supplier",
            entity_type="supplier_org",
            entity_id=org.id,
            metadata_={"reason": reason},
        )
        apply_create_audit(log, admin.id)
        db.add(log)
        return {"ok": True, "status": org.verification_status.value}

    @staticmethod
    async def restore_supplier(
        db: AsyncSession, admin: AdminAccount, application_id: UUID, reason: str | None
    ) -> dict:
        org = await db.get(SupplierOrganization, application_id)
        if not org or org.deleted_at:
            raise AppError(404, "Application not found", "not_found")
        if org.verification_status != VerificationStatus.SUSPENDED:
            raise AppError(400, "Only suspended suppliers can be restored", "invalid_status")

        org.verification_status = VerificationStatus.APPROVED
        org.storefront_published = True
        if not org.approved_at:
            org.approved_at = datetime.now(timezone.utc)
        apply_update_audit(org, admin.id)
        log = AdminActionLog(
            admin_account_id=admin.id,
            action="restore_supplier",
            entity_type="supplier_org",
            entity_id=org.id,
            metadata_={"reason": reason},
        )
        apply_create_audit(log, admin.id)
        db.add(log)
        return {"ok": True, "status": org.verification_status.value}

    # --- Verification document moderation & cleanup ---

    @staticmethod
    async def _get_registration_document(db: AsyncSession, doc_id: UUID) -> RegistrationDocument:
        doc = await db.get(RegistrationDocument, doc_id)
        if not doc or doc.deleted_at:
            raise AppError(404, "Document not found", "not_found")
        return doc

    @staticmethod
    async def approve_verification_document(
        db: AsyncSession, admin: AdminAccount, doc_id: UUID, reason: str | None
    ) -> dict:
        doc = await AdminService._get_registration_document(db, doc_id)
        doc.status = DocumentStatus.APPROVED
        apply_update_audit(doc, admin.id)

        log = AdminActionLog(
            admin_account_id=admin.id,
            action="verification_doc_approved",
            entity_type="registration_document",
            entity_id=doc.id,
            metadata_={"reason": reason},
        )
        apply_create_audit(log, admin.id)
        db.add(log)
        return {"ok": True, "status": doc.status.value}

    @staticmethod
    async def reject_verification_document(
        db: AsyncSession, admin: AdminAccount, doc_id: UUID, reason: str | None
    ) -> dict:
        doc = await AdminService._get_registration_document(db, doc_id)
        doc.status = DocumentStatus.REJECTED
        apply_update_audit(doc, admin.id)

        log = AdminActionLog(
            admin_account_id=admin.id,
            action="verification_doc_rejected",
            entity_type="registration_document",
            entity_id=doc.id,
            metadata_={"reason": reason},
        )
        apply_create_audit(log, admin.id)
        db.add(log)
        return {"ok": True, "status": doc.status.value}

    @staticmethod
    async def flag_verification_document(
        db: AsyncSession, admin: AdminAccount, doc_id: UUID, reason: str | None
    ) -> dict:
        # Represent "flagged" using REJECTED plus metadata so existing enums still apply.
        doc = await AdminService._get_registration_document(db, doc_id)
        doc.status = DocumentStatus.REJECTED
        apply_update_audit(doc, admin.id)

        log = AdminActionLog(
            admin_account_id=admin.id,
            action="verification_doc_flagged",
            entity_type="registration_document",
            entity_id=doc.id,
            metadata_={"reason": reason, "flagged": True},
        )
        apply_create_audit(log, admin.id)
        db.add(log)
        return {"ok": True, "status": doc.status.value}

    @staticmethod
    async def delete_verification_document(
        db: AsyncSession, admin: AdminAccount, doc_id: UUID, *, hard: bool = False
    ) -> dict:
        doc = await AdminService._get_registration_document(db, doc_id)
        if hard:
            await db.delete(doc)
        else:
            soft_delete(doc, admin.id)
        return {"ok": True, "id": str(doc_id), "hard": hard}

    @staticmethod
    async def delete_file_record(
        db: AsyncSession, admin: AdminAccount, file_id: UUID, *, hard: bool = False
    ) -> dict:
        record = await db.get(FileRecord, file_id)
        if not record or record.deleted_at:
            raise AppError(404, "File not found", "not_found")

        if hard:
            await db.delete(record)
        else:
            soft_delete(record, admin.id)
        return {"ok": True, "id": str(file_id), "hard": hard}

    # --- Buyer admin ---

    @staticmethod
    def _buyer_review_status(org: BuyerOrganization) -> str:
        status = org.onboarding_status
        if status == VerificationStatus.ACTION_REQUIRED:
            return "action_required"
        if status == VerificationStatus.PENDING:
            return "pending"
        if status == VerificationStatus.APPROVED:
            return "approved"
        if status == VerificationStatus.REJECTED:
            return "rejected"
        if status == VerificationStatus.SUSPENDED:
            return "suspended"
        return "pending"

    @staticmethod
    async def _buyer_primary_account(db: AsyncSession, org_id: UUID) -> BuyerAccount | None:
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
    async def _buyer_admin_message(db: AsyncSession, org_id: UUID) -> tuple[str | None, list[str]]:
        log = (
            await db.execute(
                select(AdminActionLog)
                .where(
                    AdminActionLog.entity_type == "buyer_org",
                    AdminActionLog.entity_id == org_id,
                    AdminActionLog.action == "request_buyer_info",
                    AdminActionLog.deleted_at.is_(None),
                )
                .order_by(AdminActionLog.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if not log or not log.metadata_:
            return None, []
        meta = log.metadata_
        return meta.get("message"), list(meta.get("missing_items") or [])

    @staticmethod
    def _buyer_profile_sections(
        org: BuyerOrganization,
        account: BuyerAccount | None,
        draft: BuyerRegistrationDraft | None,
    ) -> list[BuyerProfileSectionItem]:
        payload = (draft.payload if draft else None) or {}
        company = payload.get("company") or {}
        contact = payload.get("contact") or {}
        sourcing = payload.get("sourcing") or {}

        def section(key: str, label: str, ok: bool, detail: str | None = None) -> BuyerProfileSectionItem:
            return BuyerProfileSectionItem(
                key=key,
                label=label,
                status="verified" if ok else "missing",
                detail=detail,
                required=True,
            )

        categories = sourcing.get("categories") or []
        markets = sourcing.get("target_markets") or sourcing.get("targetMarkets") or []
        sourcing_detail = None
        if categories:
            sourcing_detail = ", ".join(str(c) for c in categories[:3])
        elif markets:
            sourcing_detail = ", ".join(str(m) for m in markets[:3])

        contact_name = org.procurement_contact or contact.get("contact_name") or (
            f"{account.first_name} {account.last_name}".strip() if account else ""
        )

        return [
            section(
                "company",
                "Company profile",
                bool(org.name and org.country),
                f"{org.name} · {org.country}" if org.name else None,
            ),
            section(
                "contact",
                "Procurement contact",
                bool(contact_name and account and account.email),
                contact_name or None,
            ),
            section(
                "sourcing",
                "Sourcing preferences",
                bool(categories or markets or sourcing.get("annual_import_volume")),
                sourcing_detail,
            ),
            section(
                "email",
                "Email verified",
                bool(account and account.email_verified_at),
                account.email if account else None,
            ),
        ]

    @staticmethod
    def _missing_items_from_sections(sections: list[BuyerProfileSectionItem]) -> list[str]:
        return [s.label for s in sections if s.status != "verified" and s.required]

    @staticmethod
    async def _serialize_buyer_admin(db: AsyncSession, org: BuyerOrganization) -> BuyerAdminItem:
        account = await AdminService._buyer_primary_account(db, org.id)
        draft = None
        if account:
            draft = (
                await db.execute(
                    select(BuyerRegistrationDraft).where(
                        BuyerRegistrationDraft.buyer_account_id == account.id,
                        BuyerRegistrationDraft.deleted_at.is_(None),
                    )
                )
            ).scalar_one_or_none()

        review_status = AdminService._buyer_review_status(org)
        submitted_at = org.onboarding_submitted_at or org.created_at
        hours = 0
        if submitted_at:
            ref = submitted_at if submitted_at.tzinfo else submitted_at.replace(tzinfo=timezone.utc)
            hours = max(0, int((datetime.now(timezone.utc) - ref).total_seconds() // 3600))

        admin_message, logged_missing = await AdminService._buyer_admin_message(db, org.id)
        sections = AdminService._buyer_profile_sections(org, account, draft)
        missing_items = logged_missing or AdminService._missing_items_from_sections(sections)
        info_requested = review_status == "action_required" or admin_message is not None

        location = f"{org.city}, {org.country}" if org.city else org.country
        industry = org.industry or "—"
        contact_name = org.procurement_contact or (
            f"{account.first_name} {account.last_name}".strip() if account else "—"
        )
        email = account.email if account else "—"

        rfq_count = (
            await db.execute(
                select(func.count())
                .select_from(Rfq)
                .where(Rfq.buyer_org_id == org.id, Rfq.deleted_at.is_(None))
            )
        ).scalar() or 0

        return BuyerAdminItem(
            id=org.id,
            org_id=org.id,
            company_name=org.name,
            industry=industry,
            location=location,
            contact_name=contact_name,
            email=email,
            phone=account.phone if account else None,
            website=org.website,
            job_title=org.job_title,
            submitted_at=submitted_at,
            hours_elapsed=hours,
            status=review_status,
            verified_buyer=org.verified_buyer,
            info_requested=info_requested,
            admin_message=admin_message,
            missing_items=missing_items,
            profile_sections=sections,
            rfq_count=int(rfq_count),
        )

    @staticmethod
    async def list_buyers(
        db: AsyncSession,
        *,
        status: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> BuyerAdminListResponse:
        orgs = (
            await db.execute(
                select(BuyerOrganization)
                .where(BuyerOrganization.deleted_at.is_(None))
                .order_by(BuyerOrganization.updated_at.desc())
            )
        ).scalars().all()

        pending: list[BuyerAdminItem] = []
        processed: list[BuyerAdminItem] = []
        for org in orgs:
            if org.onboarding_status == VerificationStatus.DRAFT:
                continue
            item = await AdminService._serialize_buyer_admin(db, org)
            if status == "pending" and item.status not in ("pending", "action_required"):
                continue
            if status == "approved" and item.status != "approved":
                continue
            if status == "rejected" and item.status != "rejected":
                continue
            if status == "processed" and item.status in ("pending", "action_required"):
                continue
            if item.status in ("pending", "action_required"):
                pending.append(item)
            else:
                processed.append(item)

        combined = pending + processed
        paged = paginate(combined, page, page_size)
        summary = {
            "pending": len([a for a in combined if a.status in ("pending", "action_required")]),
            "approved": len([a for a in combined if a.status == "approved"]),
            "rejected": len([a for a in combined if a.status == "rejected"]),
        }
        pending_slice = [a for a in paged.items if a.status in ("pending", "action_required")]
        processed_slice = [a for a in paged.items if a.status not in ("pending", "action_required")]
        return BuyerAdminListResponse(
            summary=summary,
            pending=pending_slice,
            processed=processed_slice,
            page=paged.page,
            page_size=paged.page_size,
            total=paged.total,
            pages=paged.pages,
        )

    @staticmethod
    async def get_buyer_detail(db: AsyncSession, org_id: UUID) -> BuyerAdminItem:
        org = await db.get(BuyerOrganization, org_id)
        if not org or org.deleted_at:
            raise AppError(404, "Buyer not found", "not_found")
        return await AdminService._serialize_buyer_admin(db, org)

    @staticmethod
    async def verify_buyer(db: AsyncSession, admin: AdminAccount, org_id: UUID, data: VerifyRequest) -> dict:
        org = await db.get(BuyerOrganization, org_id)
        if not org or org.deleted_at:
            raise AppError(404, "Buyer organization not found", "not_found")
        org.onboarding_status = VerificationStatus.APPROVED if data.approved else VerificationStatus.REJECTED
        org.verified_buyer = data.approved
        apply_update_audit(org, admin.id)
        log = AdminActionLog(
            admin_account_id=admin.id,
            action="verify_buyer",
            entity_type="buyer_org",
            entity_id=org_id,
            metadata_={"approved": data.approved, "reason": data.reason},
        )
        apply_create_audit(log, admin.id)
        db.add(log)
        return {"onboarding_status": org.onboarding_status.value, "verified_buyer": org.verified_buyer}

    @staticmethod
    async def request_buyer_info(
        db: AsyncSession, admin: AdminAccount, org_id: UUID, message: str | None
    ) -> dict:
        org = await db.get(BuyerOrganization, org_id)
        if not org or org.deleted_at:
            raise AppError(404, "Buyer not found", "not_found")
        if org.onboarding_status not in (
            VerificationStatus.PENDING,
            VerificationStatus.APPROVED,
            VerificationStatus.ACTION_REQUIRED,
        ):
            raise AppError(400, "Cannot request information for this buyer", "invalid_status")

        account = await AdminService._buyer_primary_account(db, org.id)
        draft = None
        if account:
            draft = (
                await db.execute(
                    select(BuyerRegistrationDraft).where(
                        BuyerRegistrationDraft.buyer_account_id == account.id,
                        BuyerRegistrationDraft.deleted_at.is_(None),
                    )
                )
            ).scalar_one_or_none()
        sections = AdminService._buyer_profile_sections(org, account, draft)
        missing_items = AdminService._missing_items_from_sections(sections)
        if not missing_items:
            missing_items = ["Additional company or sourcing details"]

        org.onboarding_status = VerificationStatus.ACTION_REQUIRED
        org.verified_buyer = False
        apply_update_audit(org, admin.id)

        default_message = "Please update your buyer profile with the information listed below."
        log = AdminActionLog(
            admin_account_id=admin.id,
            action="request_buyer_info",
            entity_type="buyer_org",
            entity_id=org.id,
            metadata_={
                "message": message or default_message,
                "missing_items": missing_items,
            },
        )
        apply_create_audit(log, admin.id)
        db.add(log)
        return {
            "ok": True,
            "info_requested": True,
            "status": org.onboarding_status.value,
            "missing_items": missing_items,
        }

    @staticmethod
    async def suspend_buyer(
        db: AsyncSession, admin: AdminAccount, org_id: UUID, reason: str | None
    ) -> dict:
        org = await db.get(BuyerOrganization, org_id)
        if not org or org.deleted_at:
            raise AppError(404, "Buyer not found", "not_found")
        if org.onboarding_status != VerificationStatus.APPROVED:
            raise AppError(400, "Only approved buyers can be suspended", "invalid_status")

        org.onboarding_status = VerificationStatus.SUSPENDED
        org.verified_buyer = False
        apply_update_audit(org, admin.id)
        log = AdminActionLog(
            admin_account_id=admin.id,
            action="suspend_buyer",
            entity_type="buyer_org",
            entity_id=org.id,
            metadata_={"reason": reason},
        )
        apply_create_audit(log, admin.id)
        db.add(log)
        return {"ok": True, "status": org.onboarding_status.value}

    @staticmethod
    async def restore_buyer(
        db: AsyncSession, admin: AdminAccount, org_id: UUID, reason: str | None
    ) -> dict:
        org = await db.get(BuyerOrganization, org_id)
        if not org or org.deleted_at:
            raise AppError(404, "Buyer not found", "not_found")
        if org.onboarding_status != VerificationStatus.SUSPENDED:
            raise AppError(400, "Only suspended buyers can be restored", "invalid_status")

        org.onboarding_status = VerificationStatus.APPROVED
        org.verified_buyer = True
        apply_update_audit(org, admin.id)
        log = AdminActionLog(
            admin_account_id=admin.id,
            action="restore_buyer",
            entity_type="buyer_org",
            entity_id=org.id,
            metadata_={"reason": reason},
        )
        apply_create_audit(log, admin.id)
        db.add(log)
        return {"ok": True, "status": org.onboarding_status.value}

    # --- Hard/soft delete helpers for buyers, suppliers, products ---

    @staticmethod
    async def delete_buyer_org(
        db: AsyncSession,
        admin: AdminAccount,
        org_id: UUID,
        *,
        hard: bool = False,
    ) -> dict:
        org = await db.get(BuyerOrganization, org_id)
        if not org or org.deleted_at:
            raise AppError(404, "Buyer not found", "not_found")

        members = (
            await db.execute(
                select(BuyerOrganizationMember).where(BuyerOrganizationMember.org_id == org_id)
            )
        ).scalars().all()
        account_ids = [member.buyer_account_id for member in members]

        # Do not allow hard delete while there are RFQs or orders referencing this org.
        rfq_count = (
            await db.execute(
                select(func.count())
                .select_from(Rfq)
                .where(Rfq.buyer_org_id == org.id, Rfq.deleted_at.is_(None))
            )
        ).scalar() or 0
        if hard and rfq_count > 0:
            raise AppError(409, "Cannot hard-delete buyer with RFQs", "has_rfqs")

        if hard:
            await db.execute(delete(BuyerSavedSupplier).where(BuyerSavedSupplier.buyer_org_id == org_id))
            await db.execute(delete(RegistrationDocument).where(RegistrationDocument.org_id == org_id))
            for member in members:
                await db.delete(member)
            await db.delete(org)
            for account_id in account_ids:
                await hard_purge_buyer_account(db, account_id)
        else:
            soft_delete(org, admin.id)
            for member in members:
                if not member.deleted_at:
                    soft_delete(member, admin.id)
            for account_id in account_ids:
                account = await db.get(BuyerAccount, account_id)
                if account and not account.deleted_at:
                    soft_delete(account, admin.id)

        log = AdminActionLog(
            admin_account_id=admin.id,
            action="delete_buyer_org_hard" if hard else "delete_buyer_org_soft",
            entity_type="buyer_org",
            entity_id=org.id,
            metadata_={"hard": hard, "account_ids": [str(account_id) for account_id in account_ids]},
        )
        apply_create_audit(log, admin.id)
        db.add(log)
        return {"ok": True, "id": str(org.id), "hard": hard}

    @staticmethod
    async def delete_supplier_org(
        db: AsyncSession,
        admin: AdminAccount,
        org_id: UUID,
        *,
        hard: bool = False,
    ) -> dict:
        org = await db.get(SupplierOrganization, org_id)
        if not org or org.deleted_at:
            raise AppError(404, "Supplier not found", "not_found")

        # Do not allow hard delete while there are products or orders referencing this org.
        product_count = (
            await db.execute(
                select(func.count())
                .select_from(Product)
                .where(Product.supplier_org_id == org.id, Product.deleted_at.is_(None))
            )
        ).scalar() or 0
        order_count = (
            await db.execute(
                select(func.count())
                .select_from(Order)
                .where(Order.supplier_org_id == org.id, Order.deleted_at.is_(None))
            )
        ).scalar() or 0
        if hard and (product_count > 0 or order_count > 0):
            raise AppError(409, "Cannot hard-delete supplier with products or orders", "has_dependants")

        if hard:
            await db.delete(org)
        else:
            soft_delete(org, admin.id)

        log = AdminActionLog(
            admin_account_id=admin.id,
            action="delete_supplier_org_hard" if hard else "delete_supplier_org_soft",
            entity_type="supplier_org",
            entity_id=org.id,
            metadata_={"hard": hard, "product_count": int(product_count), "order_count": int(order_count)},
        )
        apply_create_audit(log, admin.id)
        db.add(log)
        return {"ok": True, "id": str(org.id), "hard": hard}

    @staticmethod
    async def delete_product(
        db: AsyncSession,
        admin: AdminAccount,
        product_id: UUID,
        *,
        hard: bool = False,
    ) -> dict:
        product = await db.get(Product, product_id)
        if not product or product.deleted_at:
            raise AppError(404, "Product not found", "not_found")

        # For now, be conservative: prevent hard delete if there are orders or RFQs for this product.
        order_count = (
            await db.execute(
                select(func.count())
                .select_from(Order)
                .where(Order.product_id == product.id, Order.deleted_at.is_(None))
            )
        ).scalar() or 0
        rfq_count = (
            await db.execute(
                select(func.count())
                .select_from(Rfq)
                .where(Rfq.product_id == product.id, Rfq.deleted_at.is_(None))
            )
        ).scalar() or 0
        if hard and (order_count > 0 or rfq_count > 0):
            raise AppError(409, "Cannot hard-delete product with RFQs or orders", "has_dependants")

        if hard:
            await db.delete(product)
        else:
            soft_delete(product, admin.id)

        log = AdminActionLog(
            admin_account_id=admin.id,
            action="delete_product_hard" if hard else "delete_product_soft",
            entity_type="product",
            entity_id=product.id,
            metadata_={"hard": hard, "order_count": int(order_count), "rfq_count": int(rfq_count)},
        )
        apply_create_audit(log, admin.id)
        db.add(log)
        return {"ok": True, "id": str(product.id), "hard": hard}
