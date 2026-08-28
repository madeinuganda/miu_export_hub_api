from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.shared.database import get_db
from app.core.shared.exceptions import AppError
from app.core.export_hub.deps import get_current_supplier, get_supplier_org, require_approved_supplier, require_supplier_password_changed
from app.models.shared.enums import DocumentStatus, ProductStatus, SenderRole, VerificationStatus
from app.models.export_hub.misc import (
    ExportChecklistDocument,
    ExportChecklistProgress,
    ExportChecklistTemplate,
    FileRecord,
    RegistrationDocument,
    SupplierRegistrationDraft,
)
from app.services.shared.file_storage import store_upload_file, public_file_url
from app.models.export_hub.accounts import SupplierNotification
from app.models.export_hub.organizations import SupplierGalleryPhoto, SupplierOrganization
from app.models.export_hub.orders import Order
from app.models.export_hub.accounts import SupplierAccount, SupplierSession
from app.services.export_hub.admin_service import AdminService
from app.services.export_hub.catalog_service import CatalogService
from app.services.export_hub.order_service import PIPELINE_STAGE_IDS, OrderService
from app.services.export_hub.payment_service import PaymentService
from app.schemas.export_hub.payment import SupplierPaymentsListResponse, SupplierPaymentsSummary
from app.services.export_hub.rfq_service import RfqService, SubmitQuoteRequest
from app.services.export_hub.storefront_service import StorefrontService
from app.schemas.export_hub.storefront import (
    CertificationCreate,
    CertificationUpdate,
    GalleryPhotoCreate,
    GalleryPhotoUpdate,
    StorefrontCertificationItem,
    StorefrontGalleryItem,
    StorefrontResponse,
    StorefrontUpdate,
)
from app.utils.audit import apply_create_audit, apply_update_audit, soft_delete

SITE_PHOTOS_MAX = 8
SITE_PHOTO_TYPES = {"sitePhotos", "production"}

router = APIRouter(prefix="/supplier")


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
    summary = await AdminService.get_action_required_summary(db, org.id)
    if effective == "action_required" or summary.get("attentionItems"):
        payload["actionRequired"] = summary
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
    is_site_photo = document_type in SITE_PHOTO_TYPES

    if is_site_photo:
        existing_count = (
            await db.execute(
                select(func.count())
                .select_from(RegistrationDocument)
                .where(
                    RegistrationDocument.org_id == org.id,
                    RegistrationDocument.document_type.in_(SITE_PHOTO_TYPES),
                    RegistrationDocument.deleted_at.is_(None),
                )
            )
        ).scalar() or 0
        if existing_count >= SITE_PHOTOS_MAX:
            raise AppError(
                400,
                f"You can upload up to {SITE_PHOTOS_MAX} production site photos.",
                "site_photos_limit",
            )

    record = await store_upload_file(
        db,
        file=file,
        uploaded_by=account.id,
        subdirectory=f"supplier/{org.id}/registration",
    )
    file_url = public_file_url(record.storage_key)

    doc: RegistrationDocument | None = None
    if is_site_photo:
        doc = RegistrationDocument(
            org_id=org.id,
            document_type="sitePhotos",
            file_id=record.id,
            required=False,
            status=DocumentStatus.PENDING,
        )
        apply_create_audit(doc, account.id)
        db.add(doc)
        await db.flush()
    else:
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
            doc = existing
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
            await db.flush()

    gallery_photo_id: str | None = None
    if is_site_photo:
        gallery_count = (
            await db.execute(
                select(func.count())
                .select_from(SupplierGalleryPhoto)
                .where(
                    SupplierGalleryPhoto.org_id == org.id,
                    SupplierGalleryPhoto.deleted_at.is_(None),
                )
            )
        ).scalar() or 0
        photo = SupplierGalleryPhoto(
            org_id=org.id,
            image_url=file_url,
            caption=file.filename,
            sort_order=int(gallery_count),
        )
        apply_create_audit(photo, account.id)
        db.add(photo)
        await db.flush()
        gallery_photo_id = str(photo.id)

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
    file_entry = {
        "filename": file.filename,
        "fileId": str(record.id),
        "documentId": str(doc.id) if doc else None,
        "url": file_url,
        "galleryPhotoId": gallery_photo_id,
    }
    if is_site_photo:
        existing_entry = documents.get("sitePhotos")
        files: list = []
        if isinstance(existing_entry, dict):
            raw_files = existing_entry.get("files")
            if isinstance(raw_files, list):
                files = list(raw_files)
            elif existing_entry.get("fileId"):
                files = [
                    {
                        "filename": existing_entry.get("filename"),
                        "fileId": existing_entry.get("fileId"),
                        "documentId": existing_entry.get("documentId"),
                        "url": existing_entry.get("url"),
                        "galleryPhotoId": existing_entry.get("galleryPhotoId"),
                    }
                ]
        files.append(file_entry)
        documents["sitePhotos"] = {
            "uploaded": True,
            "filename": file.filename,
            "fileId": str(record.id),
            "files": files,
        }
    else:
        documents[document_type] = {
            "uploaded": True,
            "filename": file.filename,
            "fileId": str(record.id),
        }
    payload["documents"] = documents
    draft.payload = payload

    await _sync_registration_documents_from_draft(db, org, account.id)

    return {
        "documentType": document_type if not is_site_photo else "sitePhotos",
        "filename": file.filename,
        "fileId": str(record.id),
        "documentId": str(doc.id) if doc else None,
        "url": file_url,
        "galleryPhotoId": gallery_photo_id,
        "files": documents.get("sitePhotos", {}).get("files") if is_site_photo else None,
    }


@router.delete("/onboarding/documents/{document_id}")
async def delete_onboarding_document(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    account: SupplierAccount = Depends(require_supplier_password_changed),
    org: SupplierOrganization = Depends(get_supplier_org),
):
    doc = await db.get(RegistrationDocument, document_id)
    if not doc or doc.deleted_at or doc.org_id != org.id:
        raise AppError(404, "Document not found", "not_found")

    soft_delete(doc, account.id)

    draft = (
        await db.execute(
            select(SupplierRegistrationDraft).where(
                SupplierRegistrationDraft.supplier_account_id == account.id,
                SupplierRegistrationDraft.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if draft and draft.payload:
        payload = dict(draft.payload)
        documents = dict(payload.get("documents") or {})
        entry = documents.get(doc.document_type)
        if isinstance(entry, dict):
            files = entry.get("files")
            if isinstance(files, list):
                remaining = [
                    f
                    for f in files
                    if str(f.get("documentId") or "") != str(document_id)
                    and str(f.get("fileId") or "") != str(doc.file_id or "")
                ]
                if remaining:
                    last = remaining[-1]
                    documents[doc.document_type] = {
                        "uploaded": True,
                        "filename": last.get("filename"),
                        "fileId": last.get("fileId"),
                        "files": remaining,
                    }
                else:
                    documents[doc.document_type] = {"uploaded": False}
            elif str(entry.get("fileId") or "") == str(doc.file_id or ""):
                documents[doc.document_type] = {"uploaded": False}
            payload["documents"] = documents
            draft.payload = payload

    if doc.document_type in SITE_PHOTO_TYPES and doc.file_id:
        record = await db.get(FileRecord, doc.file_id)
        if record and not record.deleted_at:
            url = public_file_url(record.storage_key)
            legacy_url = f"/uploads/{record.storage_key.lstrip('/')}"
            photos = (
                await db.execute(
                    select(SupplierGalleryPhoto).where(
                        SupplierGalleryPhoto.org_id == org.id,
                        SupplierGalleryPhoto.image_url.in_([url, legacy_url]),
                        SupplierGalleryPhoto.deleted_at.is_(None),
                    )
                )
            ).scalars().all()
            for photo in photos:
                soft_delete(photo, account.id)

    return {"ok": True}


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

        file_ids: list[UUID] = []
        raw_files = entry.get("files")
        if isinstance(raw_files, list):
            for item in raw_files:
                if not isinstance(item, dict):
                    continue
                raw_fid = item.get("fileId") or item.get("file_id")
                if not raw_fid:
                    continue
                try:
                    file_ids.append(UUID(str(raw_fid)))
                except ValueError:
                    continue
        else:
            raw_fid = entry.get("fileId") or entry.get("file_id")
            if raw_fid:
                try:
                    file_ids.append(UUID(str(raw_fid)))
                except ValueError:
                    pass

        for file_id in file_ids:
            record = await db.get(FileRecord, file_id)
            if not record or record.deleted_at:
                continue

            existing = (
                await db.execute(
                    select(RegistrationDocument).where(
                        RegistrationDocument.org_id == org.id,
                        RegistrationDocument.document_type == document_type,
                        RegistrationDocument.file_id == file_id,
                        RegistrationDocument.deleted_at.is_(None),
                    )
                )
            ).scalar_one_or_none()

            if existing:
                continue

            if document_type not in SITE_PHOTO_TYPES:
                # Single-file docs: replace-in-place by type when no matching file row.
                by_type = (
                    await db.execute(
                        select(RegistrationDocument).where(
                            RegistrationDocument.org_id == org.id,
                            RegistrationDocument.document_type == document_type,
                            RegistrationDocument.deleted_at.is_(None),
                        )
                    )
                ).scalar_one_or_none()
                if by_type:
                    by_type.file_id = file_id
                    by_type.status = DocumentStatus.PENDING
                    apply_update_audit(by_type, account_id)
                    continue

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
    from app.services.shared.email_service import EmailService

    await _sync_registration_documents_from_draft(db, org, account.id)
    await AdminService._ensure_contact_document(db, org.id, account.id)
    org.verification_status = VerificationStatus.PENDING
    apply_update_audit(org, account.id)

    if account.email:
        await EmailService.send_supplier_onboarding_submitted_email(
            to_email=account.email,
            first_name=account.first_name or "there",
            company_name=org.name,
        )
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
    from app.models.export_hub.catalog import Category, Product, ProductCertification
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

    from app.services.export_hub.product_review_service import (
        ProductReviewService,
        product_status_label,
        resolve_supplier_status,
    )

    # Suppliers cannot self-publish: asking to go live queues an admin review.
    status = resolve_supplier_status(data.get("status"), None)
    p = Product(
        supplier_org_id=org.id,
        sku=data.get("sku", "PRD-NEW"),
        name=data["name"],
        category_id=resolved_category_id,
        subcategory=category_label,
        description=data.get("description"),
        origin_story=data.get("originStory") or data.get("origin_story"),
        status=status,
        moq_value=Decimal(str(data.get("moqValue", 100))),
        moq_unit=data.get("moqUnit", "kg"),
        price_amount=Decimal(str(data.get("priceAmount", 0))),
        lead_time_days=int(data["leadTimeDays"]) if data.get("leadTimeDays") is not None else None,
        stock_status=StockStatus.IN_STOCK,
        tone=data.get("tone", "coffee"),
        submitted_at=datetime.now(timezone.utc)
        if status == ProductStatus.PENDING_REVIEW
        else None,
    )
    apply_create_audit(p, account.id)
    db.add(p)
    await db.flush()

    for name in data.get("certifications") or data.get("certs") or []:
        label = str(name).strip()
        if not label:
            continue
        cert = ProductCertification(product_id=p.id, certification_name=label)
        apply_create_audit(cert, account.id)
        db.add(cert)
    await db.flush()

    if p.status == ProductStatus.PENDING_REVIEW:
        await ProductReviewService.notify_submitted(db, p)

    return {
        "id": str(p.id),
        "status": p.status.value,
        "statusLabel": product_status_label(p.status.value),
    }


@router.post("/products/{product_id}/submit")
async def submit_product_for_review(
    product_id: UUID,
    db: AsyncSession = Depends(get_db),
    org: SupplierOrganization = Depends(get_supplier_org),
    account: SupplierAccount = Depends(require_supplier_password_changed),
):
    """Send a draft (or previously rejected) listing to the MIU review queue."""
    from app.services.export_hub.product_review_service import ProductReviewService

    return await ProductReviewService.submit_for_review(db, org.id, account.id, product_id)


@router.get("/products/{product_id}")
async def supplier_product_detail(
    product_id: UUID,
    db: AsyncSession = Depends(get_db),
    org: SupplierOrganization = Depends(get_supplier_org),
    _: SupplierAccount = Depends(require_supplier_password_changed),
):
    return await CatalogService.supplier_product_detail(db, org.id, product_id)


@router.put("/products/{product_id}")
async def update_product(
    product_id: UUID,
    data: dict,
    db: AsyncSession = Depends(get_db),
    org: SupplierOrganization = Depends(get_supplier_org),
    account: SupplierAccount = Depends(require_supplier_password_changed),
):
    return await CatalogService.update_supplier_product(db, org.id, account.id, product_id, data)


@router.post("/products/{product_id}/images")
async def upload_product_image(
    product_id: UUID,
    file: UploadFile = File(...),
    is_primary: bool = Form(False),
    sort_order: int = Form(0),
    db: AsyncSession = Depends(get_db),
    org: SupplierOrganization = Depends(get_supplier_org),
    account: SupplierAccount = Depends(require_supplier_password_changed),
):
    url = await CatalogService.upload_product_image(
        db,
        org.id,
        account.id,
        product_id,
        file,
        is_primary=is_primary,
        sort_order=sort_order,
    )
    return {"url": url}


@router.get("/rfqs")
async def supplier_rfqs(status: str | None = Query(None), db: AsyncSession = Depends(get_db), org: SupplierOrganization = Depends(require_approved_supplier)):
    return {"items": await RfqService.list_supplier_rfqs(db, org.id, status)}


async def _supplier_owned_rfq(db: AsyncSession, org_id: UUID, public_id: str):
    from app.models.export_hub.rfqs import Rfq
    rfq = (await db.execute(select(Rfq).where(Rfq.public_id == public_id, Rfq.supplier_org_id == org_id))).scalar_one_or_none()
    if not rfq:
        raise AppError(404, "RFQ not found", "not_found")
    return rfq


@router.get("/rfqs/{public_id}")
async def supplier_rfq_detail(public_id: str, db: AsyncSession = Depends(get_db), org: SupplierOrganization = Depends(require_approved_supplier)):
    rfq = await _supplier_owned_rfq(db, org.id, public_id)
    from app.models.export_hub.catalog import Product
    from app.utils.formatting import format_quantity, format_relative_time, format_ugx
    product = await db.get(Product, rfq.product_id)
    st = await RfqService.supplier_inbox_status(rfq, db)
    quote = await RfqService.latest_quote(db, rfq.id)
    return {
        "id": rfq.public_id,
        "product": product.name if product else "",
        "status": st,
        "quote": (
            {
                "id": str(quote.id),
                "status": quote.status.value,
                "unitPrice": float(quote.unit_price),
                "currency": quote.currency,
                "incoterm": quote.incoterm,
                "leadTimeDays": quote.lead_time_days,
                "shipmentTerms": quote.shipment_terms,
                "notes": quote.notes,
                "adminRemarks": quote.admin_remarks,
                "submittedAt": quote.submitted_at.isoformat() if quote.submitted_at else None,
                "sentAt": quote.sent_at.isoformat() if quote.sent_at else None,
            }
            if quote
            else None
        ),
        "adminRemarks": quote.admin_remarks if quote else None,
        "sampleRequested": rfq.sample_requested,
        "received": format_relative_time(rfq.sent_at),
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
        "marketRequirements": "",
        "messages": await RfqService.list_messages_for_viewer(db, rfq.id, SenderRole.SUPPLIER),
    }


@router.get("/rfqs/{public_id}/messages")
async def supplier_rfq_messages(public_id: str, db: AsyncSession = Depends(get_db), org: SupplierOrganization = Depends(require_approved_supplier)):
    rfq = await _supplier_owned_rfq(db, org.id, public_id)
    return {"messages": await RfqService.list_messages_for_viewer(db, rfq.id, SenderRole.SUPPLIER)}


@router.post("/rfqs/{public_id}/messages")
async def supplier_send_rfq_message(
    public_id: str,
    data: MessageBodyRequest,
    db: AsyncSession = Depends(get_db),
    org: SupplierOrganization = Depends(require_approved_supplier),
    account: SupplierAccount = Depends(require_supplier_password_changed),
):
    rfq = await _supplier_owned_rfq(db, org.id, public_id)
    await RfqService.add_message(db, rfq.id, SenderRole.SUPPLIER, data.body, account.id)
    return {"ok": True}


@router.post("/rfqs/{public_id}/quote")
async def submit_quote(public_id: str, data: SubmitQuoteRequest, db: AsyncSession = Depends(get_db), org: SupplierOrganization = Depends(require_approved_supplier), account: SupplierAccount = Depends(require_supplier_password_changed)):
    """Submit a quote for MIU review; it reaches the buyer once an admin relays it."""
    return await RfqService.submit_quote(db, org.id, account.id, public_id, data)


@router.get("/rfqs/{public_id}/documents/{doc_kind}")
async def supplier_rfq_document(
    public_id: str,
    doc_kind: str,
    db: AsyncSession = Depends(get_db),
    org: SupplierOrganization = Depends(require_approved_supplier),
    _: SupplierAccount = Depends(require_supplier_password_changed),
):
    """Download the RFQ (`rfq`) or your quotation (`quote`) as a PDF."""
    from app.services.export_hub.document_endpoints import ScopedDocuments

    return await ScopedDocuments.rfq_document_response(
        db, public_id, doc_kind, supplier_org_id=org.id
    )


@router.post("/rfqs/{public_id}/decline")
async def supplier_decline_rfq(
    public_id: str,
    db: AsyncSession = Depends(get_db),
    org: SupplierOrganization = Depends(require_approved_supplier),
    account: SupplierAccount = Depends(require_supplier_password_changed),
):
    from app.models.shared.enums import RfqStatus
    rfq = await _supplier_owned_rfq(db, org.id, public_id)
    rfq.status = RfqStatus.DECLINED
    apply_update_audit(rfq, account.id)
    return {"ok": True}


@router.get("/orders/summary")
async def orders_summary(db: AsyncSession = Depends(get_db), org: SupplierOrganization = Depends(require_approved_supplier)):
    from decimal import Decimal

    from app.utils.formatting import format_ugx

    orders = (
        await db.execute(select(Order).where(Order.supplier_org_id == org.id, Order.deleted_at.is_(None)))
    ).scalars().all()
    stage_ids = [PIPELINE_STAGE_IDS[OrderService.order_pipeline_index(o)] for o in orders]
    coarse = [OrderService._coarse_supplier_status(s) for s in stage_ids]
    status_counts = {
        "payment_secured": sum(1 for s in coarse if s == "payment_secured"),
        "in_production": sum(1 for s in coarse if s == "in_production"),
        "shipped": sum(1 for s in coarse if s == "shipped"),
        "fulfilled": sum(1 for s in coarse if s == "fulfilled"),
    }
    in_production = sum(1 for s in stage_ids if s == "in_production")
    awaiting_shipment = sum(1 for s in stage_ids if s == "ready_to_dispatch")
    active_orders = [o for i, o in enumerate(orders) if stage_ids[i] != "fulfilled"]
    pipeline_value = sum((o.total_value_amount for o in active_orders), start=Decimal(0))
    pipeline = f"{in_production} in production, {awaiting_shipment} awaiting shipment"
    return {
        "active": len(active_orders),
        "pipeline": pipeline,
        "pipelineValueDisplay": format_ugx(pipeline_value),
        "statusCounts": status_counts,
    }


@router.get("/orders")
async def supplier_orders(status: str | None = None, q: str | None = None, db: AsyncSession = Depends(get_db), org: SupplierOrganization = Depends(require_approved_supplier)):
    orders = (
        await db.execute(
            select(Order).where(Order.supplier_org_id == org.id, Order.deleted_at.is_(None)).order_by(Order.created_at.desc())
        )
    ).scalars().all()
    items = []
    for o in orders:
        item = await OrderService.serialize_supplier_order_listing(db, o)
        if status and status != "all" and item["status"] != status:
            continue
        if q and q.lower() not in item["product"].lower() and q.lower() not in item["id"].lower():
            continue
        items.append(item)
    return {"items": items}


@router.get("/orders/{public_id}")
async def supplier_order_detail(public_id: str, db: AsyncSession = Depends(get_db), org: SupplierOrganization = Depends(require_approved_supplier)):
    return await OrderService.get_supplier_order_detail(db, org.id, public_id)


@router.post("/orders/{public_id}/advance")
async def advance_supplier_order(
    public_id: str,
    db: AsyncSession = Depends(get_db),
    org: SupplierOrganization = Depends(require_approved_supplier),
    account: SupplierAccount = Depends(require_supplier_password_changed),
):
    """Supplier-triggered transition: In Production -> Ready to Dispatch. Shipping and
    payment release stages remain admin-controlled."""
    return await OrderService.advance_supplier_order(db, org.id, public_id, account.id)


@router.get("/orders/{public_id}/documents/order")
async def supplier_order_document(
    public_id: str,
    db: AsyncSession = Depends(get_db),
    org: SupplierOrganization = Depends(require_approved_supplier),
    _: SupplierAccount = Depends(require_supplier_password_changed),
):
    """Order confirmation PDF."""
    from app.services.export_hub.document_endpoints import ScopedDocuments

    return await ScopedDocuments.order_document_response(
        db, public_id, supplier_org_id=org.id
    )


async def _supplier_owned_order(db: AsyncSession, org_id: UUID, public_id: str) -> Order:
    order = (await db.execute(select(Order).where(Order.public_id == public_id, Order.supplier_org_id == org_id))).scalar_one_or_none()
    if not order:
        raise AppError(404, "Order not found", "not_found")
    return order


@router.get("/orders/{public_id}/messages")
async def supplier_order_messages(public_id: str, db: AsyncSession = Depends(get_db), org: SupplierOrganization = Depends(require_approved_supplier)):
    order = await _supplier_owned_order(db, org.id, public_id)
    rfq_id = await RfqService.resolve_rfq_id_for_order(db, order)
    return {"messages": await RfqService.list_messages_for_viewer(db, rfq_id, SenderRole.SUPPLIER)}


@router.post("/orders/{public_id}/messages")
async def supplier_send_order_message(
    public_id: str,
    data: MessageBodyRequest,
    db: AsyncSession = Depends(get_db),
    org: SupplierOrganization = Depends(require_approved_supplier),
    account: SupplierAccount = Depends(require_supplier_password_changed),
):
    order = await _supplier_owned_order(db, org.id, public_id)
    rfq_id = await RfqService.resolve_rfq_id_for_order(db, order)
    await RfqService.add_message(db, rfq_id, SenderRole.SUPPLIER, data.body, account.id)
    return {"ok": True}


@router.get("/payments/summary", response_model=SupplierPaymentsSummary)
async def payments_summary(db: AsyncSession = Depends(get_db), org: SupplierOrganization = Depends(require_approved_supplier)):
    return await PaymentService.supplier_payments_summary(db, org.id)


@router.get("/payments", response_model=SupplierPaymentsListResponse)
async def payments_list(db: AsyncSession = Depends(get_db), org: SupplierOrganization = Depends(require_approved_supplier)):
    return await PaymentService.supplier_payments_list(db, org.id)


@router.get("/export-checklist")
async def export_checklist(db: AsyncSession = Depends(get_db), org: SupplierOrganization = Depends(get_supplier_org)):
    templates = (await db.execute(select(ExportChecklistTemplate).where(ExportChecklistTemplate.deleted_at.is_(None)))).scalars().all()
    progress = (await db.execute(select(ExportChecklistProgress).where(ExportChecklistProgress.org_id == org.id))).scalars().all()
    doc_rows = (
        await db.execute(
            select(ExportChecklistDocument, FileRecord)
            .join(FileRecord, FileRecord.id == ExportChecklistDocument.file_id)
            .where(ExportChecklistDocument.org_id == org.id, ExportChecklistDocument.deleted_at.is_(None))
        )
    ).all()
    prog_map = {p.item_key: p for p in progress}
    doc_map = {d.item_key: (d, f) for d, f in doc_rows}
    sections: dict[str, list] = {}
    for t in templates:
        p = prog_map.get(t.item_key)
        doc_entry = doc_map.get(t.item_key)
        sections.setdefault(t.section_id, []).append(
            {
                "key": t.item_key,
                "title": t.title,
                "description": t.description,
                "required": t.required,
                "completed": p.completed if p else False,
                "documentUrl": public_file_url(doc_entry[1].storage_key) if doc_entry else None,
                "documentFilename": doc_entry[0].filename if doc_entry else None,
            }
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


@router.post("/export-checklist/items/{item_key}/documents")
async def upload_checklist_document(
    item_key: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    org: SupplierOrganization = Depends(get_supplier_org),
    account: SupplierAccount = Depends(require_supplier_password_changed),
):
    record = await store_upload_file(
        db,
        file=file,
        uploaded_by=account.id,
        subdirectory=f"supplier/{org.id}/checklist/{item_key}",
    )

    doc = (
        await db.execute(
            select(ExportChecklistDocument).where(
                ExportChecklistDocument.org_id == org.id,
                ExportChecklistDocument.item_key == item_key,
            )
        )
    ).scalar_one_or_none()
    if doc:
        doc.file_id = record.id
        doc.filename = file.filename
        apply_update_audit(doc, account.id)
    else:
        doc = ExportChecklistDocument(org_id=org.id, item_key=item_key, file_id=record.id, filename=file.filename)
        apply_create_audit(doc, account.id)
        db.add(doc)

    # Uploading a supporting document also marks the checklist item complete.
    progress = (
        await db.execute(
            select(ExportChecklistProgress).where(
                ExportChecklistProgress.org_id == org.id,
                ExportChecklistProgress.item_key == item_key,
            )
        )
    ).scalar_one_or_none()
    if not progress:
        progress = ExportChecklistProgress(
            org_id=org.id, item_key=item_key, completed=True, completed_at=datetime.now(timezone.utc)
        )
        apply_create_audit(progress, account.id)
        db.add(progress)
    else:
        progress.completed = True
        progress.completed_at = datetime.now(timezone.utc)

    return {
        "itemKey": item_key,
        "filename": file.filename,
        "fileId": str(record.id),
        "url": public_file_url(record.storage_key),
    }


@router.get("/export-checklist/readiness")
async def checklist_readiness(db: AsyncSession = Depends(get_db), org: SupplierOrganization = Depends(get_supplier_org)):
    total = (await db.execute(select(func.count()).select_from(ExportChecklistTemplate))).scalar() or 1
    done = (await db.execute(select(func.count()).select_from(ExportChecklistProgress).where(ExportChecklistProgress.org_id == org.id, ExportChecklistProgress.completed.is_(True)))).scalar() or 0
    return {"score": int(done / total * 100), "completed": done, "total": total}


@router.get("/company-profile")
async def company_profile(
    db: AsyncSession = Depends(get_db),
    org: SupplierOrganization = Depends(get_supplier_org),
    account: SupplierAccount = Depends(require_supplier_password_changed),
):
    storefront = await StorefrontService.get_storefront(db, org)
    return {
        "name": org.name,
        "tagline": org.tagline,
        "shortDescription": org.short_description,
        "brandStory": org.brand_story,
        "website": org.website,
        "category": org.category,
        "region": org.region,
        "district": org.district,
        "location": storefront.location,
        "verified": storefront.verified,
        "verificationStatus": org.verification_status.value,
        "bannerUrl": storefront.bannerUrl,
        "bannerStyle": storefront.bannerStyle,
        "logoUrl": storefront.logoUrl,
        "slug": storefront.slug,
        "publicUrl": storefront.publicUrl,
        "gallery": [item.model_dump(mode="json") for item in storefront.gallery],
        "certifications": [item.model_dump(mode="json") for item in storefront.certifications],
        "stats": [item.model_dump(mode="json") for item in storefront.stats],
        "contact": {
            "phone": account.phone,
            "email": account.email,
            "website": org.website,
            "address": storefront.location,
        },
        "galleryMax": SITE_PHOTOS_MAX,
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


@router.get("/storefront", response_model=StorefrontResponse)
async def get_storefront(
    db: AsyncSession = Depends(get_db),
    org: SupplierOrganization = Depends(get_supplier_org),
):
    return await StorefrontService.get_storefront(db, org)


@router.put("/storefront", response_model=StorefrontResponse)
async def put_storefront(
    data: StorefrontUpdate,
    db: AsyncSession = Depends(get_db),
    org: SupplierOrganization = Depends(get_supplier_org),
    account: SupplierAccount = Depends(require_supplier_password_changed),
):
    return await StorefrontService.update_storefront(db, org, account, data)


@router.patch("/storefront/publish", response_model=StorefrontResponse)
async def publish_storefront(
    published: bool = True,
    db: AsyncSession = Depends(get_db),
    org: SupplierOrganization = Depends(require_approved_supplier),
    account: SupplierAccount = Depends(require_supplier_password_changed),
):
    return await StorefrontService.set_published(db, org, account, published)


@router.post("/storefront/banner", response_model=StorefrontResponse)
async def upload_storefront_banner(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    org: SupplierOrganization = Depends(get_supplier_org),
    account: SupplierAccount = Depends(require_supplier_password_changed),
):
    return await StorefrontService.upload_banner(db, org, account, file)


@router.post("/storefront/logo", response_model=StorefrontResponse)
async def upload_storefront_logo(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    org: SupplierOrganization = Depends(get_supplier_org),
    account: SupplierAccount = Depends(require_supplier_password_changed),
):
    return await StorefrontService.upload_logo(db, org, account, file)


@router.post("/storefront/certifications", response_model=StorefrontCertificationItem)
async def create_storefront_certification(
    data: CertificationCreate,
    db: AsyncSession = Depends(get_db),
    org: SupplierOrganization = Depends(get_supplier_org),
    account: SupplierAccount = Depends(require_supplier_password_changed),
):
    return await StorefrontService.create_certification(db, org, account, data)


@router.patch("/storefront/certifications/{cert_id}", response_model=StorefrontCertificationItem)
async def update_storefront_certification(
    cert_id: UUID,
    data: CertificationUpdate,
    db: AsyncSession = Depends(get_db),
    org: SupplierOrganization = Depends(get_supplier_org),
    account: SupplierAccount = Depends(require_supplier_password_changed),
):
    return await StorefrontService.update_certification(db, org, account, cert_id, data)


@router.delete("/storefront/certifications/{cert_id}")
async def delete_storefront_certification(
    cert_id: UUID,
    db: AsyncSession = Depends(get_db),
    org: SupplierOrganization = Depends(get_supplier_org),
    account: SupplierAccount = Depends(require_supplier_password_changed),
):
    await StorefrontService.delete_certification(db, org, account, cert_id)
    return {"ok": True}


@router.post("/storefront/gallery", response_model=StorefrontGalleryItem)
async def create_storefront_gallery_photo(
    data: GalleryPhotoCreate,
    db: AsyncSession = Depends(get_db),
    org: SupplierOrganization = Depends(get_supplier_org),
    account: SupplierAccount = Depends(require_supplier_password_changed),
):
    return await StorefrontService.create_gallery_photo(db, org, account, data)


@router.post("/storefront/gallery/upload", response_model=StorefrontGalleryItem)
async def upload_storefront_gallery_photo(
    file: UploadFile = File(...),
    caption: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
    org: SupplierOrganization = Depends(get_supplier_org),
    account: SupplierAccount = Depends(require_supplier_password_changed),
):
    gallery_count = (
        await db.execute(
            select(func.count())
            .select_from(SupplierGalleryPhoto)
            .where(
                SupplierGalleryPhoto.org_id == org.id,
                SupplierGalleryPhoto.deleted_at.is_(None),
            )
        )
    ).scalar() or 0
    if gallery_count >= SITE_PHOTOS_MAX:
        raise AppError(
            400,
            f"You can upload up to {SITE_PHOTOS_MAX} production site photos.",
            "site_photos_limit",
        )

    record = await store_upload_file(
        db,
        file=file,
        uploaded_by=account.id,
        subdirectory=f"storefront/{org.id}/gallery",
    )
    file_url = public_file_url(record.storage_key)

    # Keep registration site-photo records in sync so admin verification sees them.
    doc = RegistrationDocument(
        org_id=org.id,
        document_type="sitePhotos",
        file_id=record.id,
        required=False,
        status=DocumentStatus.PENDING,
    )
    apply_create_audit(doc, account.id)
    db.add(doc)

    return await StorefrontService.create_gallery_photo(
        db,
        org,
        account,
        GalleryPhotoCreate(
            imageUrl=file_url,
            caption=caption or file.filename,
            sortOrder=int(gallery_count),
        ),
    )


@router.patch("/storefront/gallery/{photo_id}", response_model=StorefrontGalleryItem)
async def update_storefront_gallery_photo(
    photo_id: UUID,
    data: GalleryPhotoUpdate,
    db: AsyncSession = Depends(get_db),
    org: SupplierOrganization = Depends(get_supplier_org),
    account: SupplierAccount = Depends(require_supplier_password_changed),
):
    return await StorefrontService.update_gallery_photo(db, org, account, photo_id, data)


@router.delete("/storefront/gallery/{photo_id}")
async def delete_storefront_gallery_photo(
    photo_id: UUID,
    db: AsyncSession = Depends(get_db),
    org: SupplierOrganization = Depends(get_supplier_org),
    account: SupplierAccount = Depends(require_supplier_password_changed),
):
    await StorefrontService.delete_gallery_photo(db, org, account, photo_id)
    return {"ok": True}


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
async def supplier_notif_summary(
    db: AsyncSession = Depends(get_db),
    org: SupplierOrganization = Depends(get_supplier_org),
):
    from app.models.shared.enums import VerificationStatus
    from app.services.export_hub.nav_badges_service import NavBadgesService

    if org.verification_status != VerificationStatus.APPROVED:
        return {"total": 0, "rfq": 0, "orders": 0, "messages": 0, "payments": 0}
    return await NavBadgesService.supplier_badges(db, org.id)


@router.get("/search")
async def supplier_search(q: str = Query(...)):
    return {"query": q, "results": []}


