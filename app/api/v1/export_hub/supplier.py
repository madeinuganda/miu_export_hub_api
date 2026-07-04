from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.shared.database import get_db
from app.core.export_hub.deps import get_current_supplier, get_supplier_org, require_approved_supplier, require_supplier_password_changed
from app.models.shared.enums import DocumentStatus, ProductStatus, SenderRole, VerificationStatus
from app.models.export_hub.misc import (
    ExportChecklistProgress,
    ExportChecklistTemplate,
    FileRecord,
    RegistrationDocument,
    SupplierRegistrationDraft,
)
from app.services.shared.file_storage import store_upload_file
from app.models.export_hub.accounts import SupplierNotification
from app.models.export_hub.organizations import SupplierOrganization
from app.models.export_hub.payments import PaymentEscrow
from app.models.export_hub.orders import Order
from app.models.export_hub.accounts import SupplierAccount, SupplierSession
from app.services.export_hub.admin_service import AdminService
from app.services.export_hub.catalog_service import CatalogService
from app.services.export_hub.rfq_service import RfqService, SubmitQuoteRequest
from app.utils.audit import apply_create_audit, apply_update_audit

router = APIRouter(prefix="/supplier", tags=["supplier"])


class MessageBodyRequest(BaseModel):
    body: str


def _supplier_profile_payload(org: SupplierOrganization, account: SupplierAccount) -> dict:
    initials = f"{account.first_name[:1]}{account.last_name[:1]}".upper() if account.first_name else "?"
    parts = [p for p in (org.district, org.region) if p]
    location = ", ".join(parts) if parts else "Uganda"
    if parts and "Uganda" not in location:
        location = f"{location}, Uganda"
    return {
        "verificationStatus": org.verification_status.value,
        "company": {
            "name": org.name,
            "location": location,
            "category": org.category,
            "subcategory": org.subcategory,
            "businessType": org.business_type,
            "tagline": org.tagline,
            "website": org.website,
            "shortDescription": org.short_description,
            "brandStory": org.brand_story,
            "region": org.region,
            "district": org.district,
        },
        "user": {
            "id": str(account.id),
            "email": account.email,
            "firstName": account.first_name,
            "lastName": account.last_name,
            "fullName": f"{account.first_name} {account.last_name}".strip(),
            "initials": initials,
            "phone": account.phone,
            "role": "Export Supplier",
            "twoFactorEnabled": account.two_factor_enabled,
        },
    }


@router.get("/profile")
async def supplier_profile(
    db: AsyncSession = Depends(get_db),
    org: SupplierOrganization = Depends(get_supplier_org),
    account: SupplierAccount = Depends(require_supplier_password_changed),
):
    payload = _supplier_profile_payload(org, account)
    effective = await AdminService.effective_verification_status(db, org)
    payload["verificationStatus"] = effective
    if effective == "action_required":
        payload["actionRequired"] = await AdminService.get_action_required_summary(db, org.id)
    return payload


@router.get("/dashboard")
async def supplier_dashboard(
    period: str = Query("30"),
    db: AsyncSession = Depends(get_db),
    org: SupplierOrganization = Depends(get_supplier_org),
    account: SupplierAccount = Depends(require_supplier_password_changed),
):
    if org.verification_status != VerificationStatus.APPROVED:
        payload = _supplier_profile_payload(org, account)
        payload["locked"] = True
        effective = await AdminService.effective_verification_status(db, org)
        payload["verificationStatus"] = effective
        if effective == "action_required":
            summary = await AdminService.get_action_required_summary(db, org.id)
            payload["actionRequired"] = summary
            payload["adminMessage"] = summary["message"]
        else:
            payload["adminMessage"] = (
                "Your application is under review. MIU admin will contact you within 2–3 business days."
            )
        return payload
    order_count = (await db.execute(select(func.count()).select_from(Order).where(Order.supplier_org_id == org.id, Order.deleted_at.is_(None)))).scalar()
    return {
        "verificationStatus": "approved",
        "locked": False,
        "period": period,
        "kpis": {"orders": order_count or 0, "revenue": "UGX 45,200,000", "rfqs": 3, "conversion": "68%"},
        "company": {"name": org.name, "location": f"{org.district or org.region}, Uganda"},
        "user": {
            "firstName": account.first_name,
            "fullName": f"{account.first_name} {account.last_name}",
            "initials": account.first_name[0],
            "role": "Export Supplier",
        },
    }


@router.get("/onboarding")
async def get_onboarding(
    db: AsyncSession = Depends(get_db),
    account: SupplierAccount = Depends(require_supplier_password_changed),
    org: SupplierOrganization = Depends(get_supplier_org),
):
    draft = (
        await db.execute(
            select(SupplierRegistrationDraft).where(
                SupplierRegistrationDraft.supplier_account_id == account.id,
                SupplierRegistrationDraft.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    return {
        "step": draft.step if draft else "business",
        "payload": draft.payload if draft else {},
        "onboarding_status": org.verification_status.value,
    }


@router.put("/onboarding/business")
async def onboarding_business(payload: dict, db: AsyncSession = Depends(get_db), account: SupplierAccount = Depends(require_supplier_password_changed)):
    draft = await _upsert_draft(db, account.id, "contact", payload)
    return {"step": draft.step}


@router.put("/onboarding/contact")
async def onboarding_contact(payload: dict, db: AsyncSession = Depends(get_db), account: SupplierAccount = Depends(require_supplier_password_changed)):
    draft = await _upsert_draft(db, account.id, "documents", payload)
    return {"step": draft.step}


@router.post("/onboarding/documents")
async def onboarding_documents(
    document_type: str = Form(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    account: SupplierAccount = Depends(require_supplier_password_changed),
    org: SupplierOrganization = Depends(get_supplier_org),
):
    record = await store_upload_file(
        db,
        file=file,
        uploaded_by=account.id,
        subdirectory=f"supplier/{org.id}/registration",
    )

    existing = (
        await db.execute(
            select(RegistrationDocument).where(
                RegistrationDocument.org_id == org.id,
                RegistrationDocument.document_type == document_type,
                RegistrationDocument.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()

    if existing:
        existing.file_id = record.id
        existing.status = DocumentStatus.PENDING
        apply_update_audit(existing, account.id)
    else:
        doc = RegistrationDocument(
            org_id=org.id,
            document_type=document_type,
            file_id=record.id,
            required=document_type in ("businessRegistration", "tin"),
            status=DocumentStatus.PENDING,
        )
        apply_create_audit(doc, account.id)
        db.add(doc)

    draft = (
        await db.execute(
            select(SupplierRegistrationDraft).where(
                SupplierRegistrationDraft.supplier_account_id == account.id,
                SupplierRegistrationDraft.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if not draft:
        draft = SupplierRegistrationDraft(
            supplier_account_id=account.id,
            step="documents",
            payload={},
        )
        apply_create_audit(draft, account.id)
        db.add(draft)
        await db.flush()

    payload = dict(draft.payload or {})
    documents = dict(payload.get("documents") or {})
    documents[document_type] = {
        "uploaded": True,
        "filename": file.filename,
        "fileId": str(record.id),
    }
    payload["documents"] = documents
    draft.payload = payload

    await _sync_registration_documents_from_draft(db, org, account.id)

    return {
        "documentType": document_type,
        "filename": file.filename,
        "fileId": str(record.id),
    }


async def _sync_registration_documents_from_draft(
    db: AsyncSession,
    org: SupplierOrganization,
    account_id: UUID,
) -> None:
    """Ensure registration_documents rows exist for file IDs stored on the draft."""
    draft = (
        await db.execute(
            select(SupplierRegistrationDraft).where(
                SupplierRegistrationDraft.supplier_account_id == account_id,
                SupplierRegistrationDraft.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if not draft or not draft.payload:
        return

    documents = draft.payload.get("documents")
    if not isinstance(documents, dict):
        return

    for document_type, entry in documents.items():
        if not isinstance(entry, dict):
            continue
        raw_fid = entry.get("fileId") or entry.get("file_id")
        if not raw_fid:
            continue
        try:
            file_id = UUID(str(raw_fid))
        except ValueError:
            continue

        record = await db.get(FileRecord, file_id)
        if not record or record.deleted_at:
            continue

        existing = (
            await db.execute(
                select(RegistrationDocument).where(
                    RegistrationDocument.org_id == org.id,
                    RegistrationDocument.document_type == document_type,
                    RegistrationDocument.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()

        if existing:
            existing.file_id = file_id
            existing.status = DocumentStatus.PENDING
            apply_update_audit(existing, account_id)
        else:
            doc = RegistrationDocument(
                org_id=org.id,
                document_type=document_type,
                file_id=file_id,
                required=document_type in ("businessRegistration", "tin"),
                status=DocumentStatus.PENDING,
            )
            apply_create_audit(doc, account_id)
            db.add(doc)


@router.post("/onboarding/submit")
async def onboarding_submit(
    db: AsyncSession = Depends(get_db),
    org: SupplierOrganization = Depends(get_supplier_org),
    account: SupplierAccount = Depends(require_supplier_password_changed),
):
    await _sync_registration_documents_from_draft(db, org, account.id)
    org.verification_status = VerificationStatus.PENDING
    apply_update_audit(org, account.id)
    return {"status": "pending"}


@router.get("/onboarding/status")
async def onboarding_status(
    db: AsyncSession = Depends(get_db),
    org: SupplierOrganization = Depends(get_supplier_org),
):
    status = await AdminService.effective_verification_status(db, org)
    return {"verificationStatus": status, "onboarding_status": status}


async def _upsert_draft(db: AsyncSession, account_id: UUID, step: str, payload: dict) -> SupplierRegistrationDraft:
    draft = (
        await db.execute(
            select(SupplierRegistrationDraft).where(
                SupplierRegistrationDraft.supplier_account_id == account_id,
                SupplierRegistrationDraft.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if not draft:
        draft = SupplierRegistrationDraft(supplier_account_id=account_id, step=step, payload=payload)
        apply_create_audit(draft, account_id)
        db.add(draft)
    else:
        draft.step = step
        draft.payload = {**(draft.payload or {}), **payload}
    return draft


@router.get("/categories")
async def supplier_categories(
    db: AsyncSession = Depends(get_db),
    _: SupplierAccount = Depends(require_supplier_password_changed),
):
    from app.services.export_hub.category_service import CategoryService

    resp = await CategoryService.list_categories(db, active_only=True)
    return {"items": [{"id": str(i.id), "slug": i.slug, "label": i.label} for i in resp.items]}


@router.get("/products")
async def supplier_products(
    q: str | None = None,
    db: AsyncSession = Depends(get_db),
    org: SupplierOrganization = Depends(get_supplier_org),
    account: SupplierAccount = Depends(require_supplier_password_changed),
):
    return await CatalogService.supplier_products(db, org.id, q)


@router.post("/products")
async def create_product(
    data: dict,
    db: AsyncSession = Depends(get_db),
    org: SupplierOrganization = Depends(get_supplier_org),
    account: SupplierAccount = Depends(require_supplier_password_changed),
):
    from decimal import Decimal
    from app.core.shared.exceptions import AppError
    from app.models.export_hub.catalog import Category, Product
    from app.models.shared.enums import StockStatus

    raw_category_id = data.get("categoryId") or data.get("category_id")
    category_label = data.get("category")
    resolved_category_id: UUID | None = None
    if raw_category_id:
        try:
            resolved_category_id = UUID(str(raw_category_id))
        except ValueError as exc:
            raise AppError(400, "Invalid category id", "validation_error") from exc
        cat = await db.get(Category, resolved_category_id)
        if not cat or cat.deleted_at or not cat.is_active:
            raise AppError(400, "Category not found or inactive", "invalid_category")
        category_label = cat.label

    status_raw = str(data.get("status", "draft")).lower()
    p = Product(
        supplier_org_id=org.id,
        sku=data.get("sku", "PRD-NEW"),
        name=data["name"],
        category_id=resolved_category_id,
        subcategory=category_label,
        description=data.get("description"),
        origin_story=data.get("originStory") or data.get("origin_story"),
        status=ProductStatus.DRAFT if status_raw == "draft" else ProductStatus.PUBLISHED,
        moq_value=Decimal(str(data.get("moqValue", 100))),
        moq_unit=data.get("moqUnit", "kg"),
        price_amount=Decimal(str(data.get("priceAmount", 0))),
        lead_time_days=int(data["leadTimeDays"]) if data.get("leadTimeDays") is not None else None,
        stock_status=StockStatus.IN_STOCK,
        tone=data.get("tone", "coffee"),
    )
    apply_create_audit(p, account.id)
    db.add(p)
    await db.flush()
    return {"id": str(p.id)}


@router.get("/rfqs")
async def supplier_rfqs(status: str | None = Query(None), db: AsyncSession = Depends(get_db), org: SupplierOrganization = Depends(require_approved_supplier)):
    return {"items": await RfqService.list_supplier_rfqs(db, org.id, status)}


@router.get("/rfqs/{public_id}")
async def supplier_rfq_detail(public_id: str, db: AsyncSession = Depends(get_db), org: SupplierOrganization = Depends(require_approved_supplier)):
    from app.models.export_hub.rfqs import Rfq
    rfq = (await db.execute(select(Rfq).where(Rfq.public_id == public_id, Rfq.supplier_org_id == org.id))).scalar_one_or_none()
    if not rfq:
        from app.core.shared.exceptions import AppError
        raise AppError(404, "RFQ not found", "not_found")
    from app.models.export_hub.catalog import Product
    from app.utils.formatting import format_quantity, format_ugx
    product = await db.get(Product, rfq.product_id)
    st = await RfqService.supplier_inbox_status(rfq, db)
    return {
        "id": rfq.public_id,
        "product": product.name if product else "",
        "status": st,
        "sampleRequested": rfq.sample_requested,
        "received": rfq.sent_at.date().isoformat() if rfq.sent_at else "",
        "buyer": "via MIU Admin",
        "destination": rfq.destination_port or "",
        "destinationFlag": "🌍",
        "port": rfq.destination_port or "",
        "quantity": format_quantity(rfq.quantity, rfq.unit),
        "quantityNum": float(rfq.quantity),
        "targetPrice": format_ugx(rfq.target_price_amount or 0, rfq.unit),
        "targetPriceNum": float(rfq.target_price_amount or 0),
        "requiredBy": rfq.required_by_date.isoformat() if rfq.required_by_date else "",
        "certifications": [],
        "marketRequirements": rfq.message or "",
        "messages": [],
    }


@router.post("/rfqs/{public_id}/quote")
async def submit_quote(public_id: str, data: SubmitQuoteRequest, db: AsyncSession = Depends(get_db), org: SupplierOrganization = Depends(require_approved_supplier), account: SupplierAccount = Depends(require_supplier_password_changed)):
    return await RfqService.submit_quote(db, org.id, account.id, public_id, data)


@router.get("/orders/summary")
async def orders_summary(db: AsyncSession = Depends(get_db), org: SupplierOrganization = Depends(require_approved_supplier)):
    count = (await db.execute(select(func.count()).select_from(Order).where(Order.supplier_org_id == org.id, Order.deleted_at.is_(None)))).scalar()
    return {"active": count or 0, "pipeline": "2 in production, 1 awaiting shipment"}


@router.get("/orders")
async def supplier_orders(status: str | None = None, q: str | None = None, db: AsyncSession = Depends(get_db), org: SupplierOrganization = Depends(require_approved_supplier)):
    from app.services.export_hub.order_service import OrderService
    orders = (await db.execute(select(Order).where(Order.supplier_org_id == org.id, Order.deleted_at.is_(None)))).scalars().all()
    items = []
    for o in orders:
        if status and o.status.value != status:
            continue
        items.append(await OrderService._serialize_order_listing(db, o, "active"))
    return {"items": items}


@router.put("/orders/{public_id}/status")
async def update_order_status(public_id: str, status: str, db: AsyncSession = Depends(get_db), org: SupplierOrganization = Depends(require_approved_supplier), account: SupplierAccount = Depends(require_supplier_password_changed)):
    from app.models.shared.enums import OrderStatus
    order = (await db.execute(select(Order).where(Order.public_id == public_id, Order.supplier_org_id == org.id))).scalar_one_or_none()
    if order:
        order.status = OrderStatus(status)
        apply_update_audit(order, account.id)
    return {"ok": True}


@router.get("/payments/summary")
async def payments_summary(db: AsyncSession = Depends(get_db), org: SupplierOrganization = Depends(require_approved_supplier)):
    escrows = (
        await db.execute(
            select(PaymentEscrow)
            .join(Order, Order.id == PaymentEscrow.order_id)
            .where(Order.supplier_org_id == org.id, PaymentEscrow.deleted_at.is_(None))
        )
    ).scalars().all()
    total = sum(e.total_amount for e in escrows)
    return {"totalEscrow": f"UGX {int(total):,}", "upfrontReceived": "70%", "balancePending": "30%", "activeOrders": len(escrows)}


@router.get("/payments")
async def payments_list(db: AsyncSession = Depends(get_db), org: SupplierOrganization = Depends(require_approved_supplier)):
    return {"items": [], "tradeAssurance": {"upfrontPercent": 70, "balancePercent": 30}}


@router.get("/export-checklist")
async def export_checklist(db: AsyncSession = Depends(get_db), org: SupplierOrganization = Depends(get_supplier_org)):
    templates = (await db.execute(select(ExportChecklistTemplate).where(ExportChecklistTemplate.deleted_at.is_(None)))).scalars().all()
    progress = (await db.execute(select(ExportChecklistProgress).where(ExportChecklistProgress.org_id == org.id))).scalars().all()
    prog_map = {p.item_key: p for p in progress}
    sections: dict[str, list] = {}
    for t in templates:
        p = prog_map.get(t.item_key)
        sections.setdefault(t.section_id, []).append(
            {"key": t.item_key, "title": t.title, "description": t.description, "required": t.required, "completed": p.completed if p else False}
        )
    return {"sections": [{"id": k, "items": v} for k, v in sections.items()]}


@router.put("/export-checklist/items/{item_key}")
async def toggle_checklist(item_key: str, completed: bool = True, db: AsyncSession = Depends(get_db), org: SupplierOrganization = Depends(get_supplier_org), account: SupplierAccount = Depends(require_supplier_password_changed)):
    row = (
        await db.execute(select(ExportChecklistProgress).where(ExportChecklistProgress.org_id == org.id, ExportChecklistProgress.item_key == item_key))
    ).scalar_one_or_none()
    if not row:
        row = ExportChecklistProgress(org_id=org.id, item_key=item_key, completed=completed, completed_at=datetime.now(timezone.utc) if completed else None)
        apply_create_audit(row, account.id)
        db.add(row)
    else:
        row.completed = completed
        row.completed_at = datetime.now(timezone.utc) if completed else None
    return {"ok": True}


@router.get("/export-checklist/readiness")
async def checklist_readiness(db: AsyncSession = Depends(get_db), org: SupplierOrganization = Depends(get_supplier_org)):
    total = (await db.execute(select(func.count()).select_from(ExportChecklistTemplate))).scalar() or 1
    done = (await db.execute(select(func.count()).select_from(ExportChecklistProgress).where(ExportChecklistProgress.org_id == org.id, ExportChecklistProgress.completed.is_(True)))).scalar() or 0
    return {"score": int(done / total * 100), "completed": done, "total": total}


@router.get("/company-profile")
async def company_profile(org: SupplierOrganization = Depends(get_supplier_org)):
    return {
        "name": org.name,
        "tagline": org.tagline,
        "shortDescription": org.short_description,
        "brandStory": org.brand_story,
        "website": org.website,
        "category": org.category,
        "region": org.region,
        "district": org.district,
    }


@router.put("/company-profile")
async def update_company_profile(data: dict, org: SupplierOrganization = Depends(get_supplier_org), account: SupplierAccount = Depends(require_supplier_password_changed), db: AsyncSession = Depends(get_db)):
    for field in ("tagline", "short_description", "brand_story", "website", "category", "region", "district"):
        key = field.replace("_", "")
        camel = "".join([w.capitalize() if i else w for i, w in enumerate(field.split("_"))])
        if camel in data or field in data:
            setattr(org, field, data.get(camel, data.get(field)))
    apply_update_audit(org, account.id)
    return {"ok": True}


@router.get("/storefront")
async def get_storefront(org: SupplierOrganization = Depends(get_supplier_org)):
    return {"published": org.storefront_published, "slug": org.slug}


@router.put("/storefront")
async def put_storefront(published: bool = True, org: SupplierOrganization = Depends(require_approved_supplier), account: SupplierAccount = Depends(require_supplier_password_changed)):
    org.storefront_published = published
    return {"published": published}


@router.get("/notifications")
async def supplier_notifications(db: AsyncSession = Depends(get_db), account: SupplierAccount = Depends(require_supplier_password_changed)):
    rows = (
        await db.execute(
            select(SupplierNotification)
            .where(
                SupplierNotification.supplier_account_id == account.id,
                SupplierNotification.deleted_at.is_(None),
            )
            .order_by(SupplierNotification.created_at.desc())
        )
    ).scalars().all()
    return {
        "items": [
            {"id": str(n.id), "title": n.title, "body": n.body, "time": "recent", "unread": n.read_at is None, "icon": n.icon_key or "message", "iconTone": "green"}
            for n in rows
        ]
    }


@router.post("/notifications/{notif_id}/read")
async def mark_read(notif_id: UUID, db: AsyncSession = Depends(get_db), account: SupplierAccount = Depends(require_supplier_password_changed)):
    n = await db.get(SupplierNotification, notif_id)
    if n and n.supplier_account_id == account.id:
        n.read_at = datetime.now(timezone.utc)
    return {"ok": True}


@router.get("/notifications/summary")
async def supplier_notif_summary(account: SupplierAccount = Depends(require_supplier_password_changed), db: AsyncSession = Depends(get_db)):
    unread = (
        await db.execute(
            select(func.count())
            .select_from(SupplierNotification)
            .where(
                SupplierNotification.supplier_account_id == account.id,
                SupplierNotification.read_at.is_(None),
            )
        )
    ).scalar()
    return {"total": unread or 3, "rfq": 1, "orders": 1, "messages": 1}


@router.get("/search")
async def supplier_search(q: str = Query(...)):
    return {"query": q, "results": []}


@router.get("/conversations/miu-admin")
async def supplier_chat(db: AsyncSession = Depends(get_db), org: SupplierOrganization = Depends(get_supplier_org)):
    from app.models.shared.enums import ConversationType
    from app.models.export_hub.messaging import ConversationMessage, ConversationThread
    thread = (
        await db.execute(
            select(ConversationThread).where(
                ConversationThread.supplier_org_id == org.id, ConversationThread.thread_type == ConversationType.SUPPLIER_MIU
            )
        )
    ).scalar_one_or_none()
    if not thread:
        return {"messages": []}
    msgs = (await db.execute(select(ConversationMessage).where(ConversationMessage.thread_id == thread.id).order_by(ConversationMessage.sent_at))).scalars().all()
    return {"messages": [{"id": str(m.id), "from": m.sender_role.value, "body": m.body, "time": m.sent_at.isoformat()} for m in msgs]}


@router.post("/conversations/miu-admin/messages")
async def supplier_send_msg(
    data: MessageBodyRequest,
    db: AsyncSession = Depends(get_db),
    org: SupplierOrganization = Depends(get_supplier_org),
    account: SupplierAccount = Depends(require_supplier_password_changed),
):
    from app.models.shared.enums import ConversationType
    from app.models.export_hub.messaging import ConversationMessage, ConversationThread
    thread = (
        await db.execute(select(ConversationThread).where(ConversationThread.supplier_org_id == org.id, ConversationThread.thread_type == ConversationType.SUPPLIER_MIU))
    ).scalar_one_or_none()
    if not thread:
        thread = ConversationThread(thread_type=ConversationType.SUPPLIER_MIU, supplier_org_id=org.id, subject="MIU Admin")
        apply_create_audit(thread, account.id)
        db.add(thread)
        await db.flush()
    msg = ConversationMessage(thread_id=thread.id, sender_role=SenderRole.SUPPLIER, body=data.body, sent_at=datetime.now(timezone.utc))
    apply_create_audit(msg, account.id)
    db.add(msg)
    return {"ok": True}
