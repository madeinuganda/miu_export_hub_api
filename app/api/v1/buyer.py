from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import (
    get_buyer_org,
    get_current_buyer,
    require_buyer_password_changed,
    require_onboarded_buyer_org_id,
)
from app.models.enums import SenderRole
from app.models.misc import BuyerRegistrationDraft, BuyerSavedSupplier
from app.models.organizations import BuyerOrganization, SupplierOrganization
from app.models.orders import Order
from app.models.rfqs import Rfq
from app.models.accounts import (
    BuyerAccount,
    BuyerAddress,
    BuyerNotification,
    BuyerNotificationSetting,
    BuyerPreference,
    BuyerSession,
)
from app.services.buyer_onboarding_service import BuyerOnboardingService
from app.services.catalog_service import CatalogService
from app.services.order_service import OrderService
from app.services.rfq_service import CreateRfqRequest, RfqService
from app.utils.audit import apply_create_audit, apply_update_audit, soft_delete

router = APIRouter(prefix="/buyer", tags=["buyer"])


def _buyer_profile_payload(
    org: BuyerOrganization,
    account: BuyerAccount,
    draft_payload: dict | None = None,
) -> dict:
    payload = draft_payload or {}
    company_draft = payload.get("company") or {}
    contact_draft = payload.get("contact") or {}
    sourcing_draft = payload.get("sourcing") or {}

    city = org.city or company_draft.get("city")
    country = org.country or company_draft.get("country") or ""
    location_parts = [p for p in (city, country) if p]
    location = ", ".join(location_parts) if location_parts else country or "—"

    initials = (
        f"{account.first_name[:1]}{account.last_name[:1]}".upper()
        if account.first_name and account.last_name
        else (account.first_name[:1] if account.first_name else "?").upper()
    )

    return {
        "onboardingStatus": org.onboarding_status.value,
        "verifiedBuyer": org.verified_buyer,
        "verifiedLabel": "Verified Buyer" if org.verified_buyer else "Buyer",
        "company": {
            "name": org.name,
            "country": country,
            "city": city,
            "industry": org.industry or company_draft.get("industry"),
            "website": org.website or company_draft.get("website"),
            "location": location,
            "procurementContact": org.procurement_contact or contact_draft.get("contact_name"),
            "jobTitle": org.job_title or contact_draft.get("job_title"),
        },
        "user": {
            "id": str(account.id),
            "email": account.email,
            "firstName": account.first_name,
            "lastName": account.last_name,
            "fullName": f"{account.first_name} {account.last_name}".strip(),
            "initials": initials,
            "phone": account.phone or contact_draft.get("phone"),
            "role": "Buyer",
            "jobTitle": org.job_title or contact_draft.get("job_title"),
            "twoFactorEnabled": account.two_factor_enabled,
            "emailVerified": account.email_verified_at is not None,
        },
        "sourcing": {
            "categories": sourcing_draft.get("categories") or [],
            "targetMarkets": sourcing_draft.get("target_markets") or [],
            "annualImportVolume": sourcing_draft.get("annual_import_volume"),
            "paymentTerm": sourcing_draft.get("payment_term"),
            "certifications": sourcing_draft.get("certifications") or [],
            "notes": sourcing_draft.get("notes"),
            "businessType": company_draft.get("business_type") or org.industry,
            "companyBio": company_draft.get("company_bio"),
        },
    }


@router.get("/profile")
async def buyer_profile(
    db: AsyncSession = Depends(get_db),
    org: BuyerOrganization = Depends(get_buyer_org),
    account: BuyerAccount = Depends(require_buyer_password_changed),
):
    draft = (
        await db.execute(
            select(BuyerRegistrationDraft).where(
                BuyerRegistrationDraft.buyer_account_id == account.id,
                BuyerRegistrationDraft.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    draft_payload = draft.payload if draft and draft.payload else {}
    status = BuyerOnboardingService.status_response(org)
    orders_placed = (
        await db.execute(
            select(func.count()).select_from(Order).where(
                Order.buyer_org_id == org.id,
                Order.deleted_at.is_(None),
            )
        )
    ).scalar() or 0
    return {
        **_buyer_profile_payload(org, account, draft_payload),
        "adminMessage": status.get("admin_message"),
        "memberSince": account.created_at.isoformat() if account.created_at else None,
        "ordersPlaced": int(orders_placed),
    }


class BuyerAccountProfileUpdate(BaseModel):
    first_name: str
    last_name: str
    phone: str | None = None


@router.patch("/profile/account")
async def update_buyer_account_profile(
    data: BuyerAccountProfileUpdate,
    db: AsyncSession = Depends(get_db),
    org: BuyerOrganization = Depends(get_buyer_org),
    account: BuyerAccount = Depends(require_buyer_password_changed),
):
    account.first_name = data.first_name.strip()
    account.last_name = data.last_name.strip()
    account.phone = data.phone
    apply_update_audit(account, account.id)
    draft = (
        await db.execute(
            select(BuyerRegistrationDraft).where(
                BuyerRegistrationDraft.buyer_account_id == account.id,
                BuyerRegistrationDraft.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    draft_payload = draft.payload if draft and draft.payload else {}
    return _buyer_profile_payload(org, account, draft_payload)


@router.put("/profile/company")
async def update_buyer_company_profile(
    data: dict,
    db: AsyncSession = Depends(get_db),
    account: BuyerAccount = Depends(require_buyer_password_changed),
    org: BuyerOrganization = Depends(get_buyer_org),
):
    from app.schemas.buyer_onboarding import BuyerCompanyStep

    step = BuyerCompanyStep(
        company_name=data.get("company_name") or org.name,
        country=data.get("country") or org.country,
        city=data.get("city"),
        industry=data.get("industry"),
        website=data.get("website"),
    )
    await BuyerOnboardingService.save_company(db, account.id, step)
    org.name = step.company_name
    org.country = step.country
    org.city = step.city
    org.industry = step.industry
    org.website = step.website
    apply_update_audit(org, account.id)
    draft = (
        await db.execute(
            select(BuyerRegistrationDraft).where(
                BuyerRegistrationDraft.buyer_account_id == account.id,
                BuyerRegistrationDraft.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    draft_payload = draft.payload if draft and draft.payload else {}
    if draft and data.get("company_bio"):
        payload = dict(draft.payload or {})
        company = dict(payload.get("company") or {})
        company["company_bio"] = data.get("company_bio")
        payload["company"] = company
        draft.payload = payload
    return _buyer_profile_payload(org, account, draft_payload)


@router.put("/profile/sourcing")
async def update_buyer_sourcing_profile(
    data: dict,
    db: AsyncSession = Depends(get_db),
    account: BuyerAccount = Depends(require_buyer_password_changed),
    org: BuyerOrganization = Depends(get_buyer_org),
):
    from app.schemas.buyer_onboarding import BuyerSourcingStep

    step = BuyerSourcingStep(
        categories=data.get("categories") or [],
        target_markets=data.get("target_markets") or [],
        annual_import_volume=data.get("annual_import_volume"),
        notes=data.get("notes"),
    )
    await BuyerOnboardingService.save_sourcing(db, account.id, step)
    draft = (
        await db.execute(
            select(BuyerRegistrationDraft).where(
                BuyerRegistrationDraft.buyer_account_id == account.id,
                BuyerRegistrationDraft.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    draft_payload = draft.payload if draft and draft.payload else {}
    if data.get("payment_term") and draft:
        payload = dict(draft.payload or {})
        sourcing = dict(payload.get("sourcing") or {})
        sourcing["payment_term"] = data.get("payment_term")
        payload["sourcing"] = sourcing
        draft.payload = payload
    if data.get("certifications") and draft:
        payload = dict(draft.payload or {})
        sourcing = dict(payload.get("sourcing") or {})
        sourcing["certifications"] = data.get("certifications")
        payload["sourcing"] = sourcing
        draft.payload = payload
    return _buyer_profile_payload(org, account, draft_payload)


@router.get("/browse")
async def buyer_browse(
    category_id: UUID | None = None,
    q: str | None = None,
    db: AsyncSession = Depends(get_db),
    org: BuyerOrganization = Depends(get_buyer_org),
    _: BuyerAccount = Depends(require_buyer_password_changed),
):
    return await CatalogService.buyer_browse(db, category_id, q, customer_type=org.industry)


@router.get("/products")
async def buyer_products(
    category_id: UUID | None = None,
    supplier_org_id: UUID | None = None,
    q: str | None = None,
    db: AsyncSession = Depends(get_db),
    org: BuyerOrganization = Depends(get_buyer_org),
    _: BuyerAccount = Depends(require_buyer_password_changed),
):
    data = await CatalogService.buyer_browse(db, category_id, q, customer_type=org.industry)
    if supplier_org_id:
        from app.models.catalog import Product
        from app.models.enums import ProductStatus
        result = await db.execute(
            select(Product).where(
                Product.supplier_org_id == supplier_org_id,
                Product.status == ProductStatus.PUBLISHED.value,
                Product.deleted_at.is_(None),
            )
        )
        data["products"] = [await CatalogService._buyer_listing(db, p) for p in result.scalars().all()]
    return data


@router.get("/products/{product_id}")
async def buyer_product(product_id: UUID, db: AsyncSession = Depends(get_db), _: BuyerAccount = Depends(require_buyer_password_changed)):
    return await CatalogService.buyer_product_detail(db, product_id)


@router.post("/rfqs")
async def create_rfq(
    data: CreateRfqRequest,
    db: AsyncSession = Depends(get_db),
    org_id: UUID = Depends(require_onboarded_buyer_org_id),
    account: BuyerAccount = Depends(require_buyer_password_changed),
):
    rfq = await RfqService.create_rfq(db, org_id, account.id, data)
    return {"id": rfq.public_id}


@router.get("/rfqs")
async def list_rfqs(db: AsyncSession = Depends(get_db), org_id: UUID = Depends(require_onboarded_buyer_org_id), _: BuyerAccount = Depends(require_buyer_password_changed)):
    return await RfqService.list_buyer_rfqs(db, org_id)


@router.get("/rfqs/{public_id}")
async def get_rfq(public_id: str, db: AsyncSession = Depends(get_db), org_id: UUID = Depends(require_onboarded_buyer_org_id), _: BuyerAccount = Depends(require_buyer_password_changed)):
    return await RfqService.get_buyer_rfq(db, org_id, public_id)


@router.post("/rfqs/{public_id}/accept")
async def accept_rfq(
    public_id: str,
    db: AsyncSession = Depends(get_db),
    org_id: UUID = Depends(require_onboarded_buyer_org_id),
    account: BuyerAccount = Depends(require_buyer_password_changed),
):
    return await OrderService.accept_rfq(db, org_id, account.id, public_id)


@router.post("/rfqs/{public_id}/decline")
async def decline_rfq(public_id: str, db: AsyncSession = Depends(get_db), org_id: UUID = Depends(require_onboarded_buyer_org_id), account: BuyerAccount = Depends(require_buyer_password_changed)):
    from app.models.enums import RfqStatus
    rfq = (await db.execute(select(Rfq).where(Rfq.public_id == public_id, Rfq.buyer_org_id == org_id))).scalar_one_or_none()
    if rfq:
        rfq.status = RfqStatus.DECLINED
    return {"ok": True}


class RfqMessageRequest(BaseModel):
    body: str


class MessageBodyRequest(BaseModel):
    body: str


@router.post("/rfqs/{public_id}/messages")
async def rfq_message(
    public_id: str,
    data: RfqMessageRequest,
    db: AsyncSession = Depends(get_db),
    org_id: UUID = Depends(require_onboarded_buyer_org_id),
    account: BuyerAccount = Depends(require_buyer_password_changed),
):
    rfq = (await db.execute(select(Rfq).where(Rfq.public_id == public_id, Rfq.buyer_org_id == org_id))).scalar_one_or_none()
    if rfq:
        await RfqService.add_message(db, rfq.id, SenderRole.BUYER, data.body, account.id)
    return {"ok": True}


@router.get("/orders")
async def buyer_orders(tab: str | None = Query(None), db: AsyncSession = Depends(get_db), org_id: UUID = Depends(require_onboarded_buyer_org_id), _: BuyerAccount = Depends(require_buyer_password_changed)):
    return {"items": await OrderService.list_buyer_orders(db, org_id, tab)}


@router.get("/orders/{public_id}")
async def buyer_order_detail(public_id: str, db: AsyncSession = Depends(get_db), org_id: UUID = Depends(require_onboarded_buyer_org_id), _: BuyerAccount = Depends(require_buyer_password_changed)):
    return await OrderService.get_buyer_order_detail(db, org_id, public_id)


@router.get("/orders/{public_id}/invoice")
async def buyer_invoice(public_id: str):
    return {"url": f"/uploads/invoices/{public_id}.pdf", "stub": True}


@router.get("/orders/{public_id}/tracking")
async def buyer_tracking(public_id: str, db: AsyncSession = Depends(get_db), org_id: UUID = Depends(require_onboarded_buyer_org_id), _: BuyerAccount = Depends(require_buyer_password_changed)):
    detail = await OrderService.get_buyer_order_detail(db, org_id, public_id)
    return {"trackingNumber": detail.get("trackingNumber"), "eta": detail.get("eta")}


@router.post("/orders/{public_id}/reorder")
async def reorder(public_id: str, db: AsyncSession = Depends(get_db), org_id: UUID = Depends(require_onboarded_buyer_org_id), account: BuyerAccount = Depends(require_buyer_password_changed)):
    from app.models.orders import Order
    order = (await db.execute(select(Order).where(Order.public_id == public_id, Order.buyer_org_id == org_id))).scalar_one_or_none()
    if not order:
        from app.core.exceptions import AppError
        raise AppError(404, "Order not found", "not_found")
    rfq = await RfqService.create_rfq(
        db, org_id, account.id, CreateRfqRequest(product_id=order.product_id, quantity=order.quantity, unit=order.unit)
    )
    return {"id": rfq.public_id}


@router.get("/saved-suppliers")
async def saved_suppliers(q: str | None = None, db: AsyncSession = Depends(get_db), org_id: UUID = Depends(require_onboarded_buyer_org_id), _: BuyerAccount = Depends(require_buyer_password_changed)):
    rows = (await db.execute(select(BuyerSavedSupplier).where(BuyerSavedSupplier.buyer_org_id == org_id, BuyerSavedSupplier.deleted_at.is_(None)))).scalars().all()
    items = []
    for row in rows:
        org = await db.get(SupplierOrganization, row.supplier_org_id)
        if org and (not q or q.lower() in org.name.lower()):
            items.append({"id": str(org.id), "name": org.name, "location": f"{org.district or org.region}, Uganda", "category": org.category})
    return {"items": items}


@router.post("/saved-suppliers")
async def save_supplier(supplier_org_id: UUID, db: AsyncSession = Depends(get_db), org_id: UUID = Depends(require_onboarded_buyer_org_id), account: BuyerAccount = Depends(require_buyer_password_changed)):
    row = BuyerSavedSupplier(buyer_org_id=org_id, supplier_org_id=supplier_org_id)
    apply_create_audit(row, account.id)
    db.add(row)
    return {"ok": True}


@router.delete("/saved-suppliers/{supplier_org_id}")
async def unsave_supplier(supplier_org_id: UUID, db: AsyncSession = Depends(get_db), org_id: UUID = Depends(require_onboarded_buyer_org_id), account: BuyerAccount = Depends(require_buyer_password_changed)):
    row = (
        await db.execute(
            select(BuyerSavedSupplier).where(
                BuyerSavedSupplier.buyer_org_id == org_id,
                BuyerSavedSupplier.supplier_org_id == supplier_org_id,
                BuyerSavedSupplier.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if row:
        soft_delete(row, account.id)
    return {"ok": True}


@router.get("/conversations/miu-account-manager")
async def buyer_conversation(db: AsyncSession = Depends(get_db), org_id: UUID = Depends(require_onboarded_buyer_org_id), _: BuyerAccount = Depends(require_buyer_password_changed)):
    from app.models.enums import ConversationType
    from app.models.messaging import ConversationMessage, ConversationThread
    thread = (
        await db.execute(
            select(ConversationThread).where(
                ConversationThread.buyer_org_id == org_id,
                ConversationThread.thread_type == ConversationType.BUYER_MIU,
                ConversationThread.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if not thread:
        return {"messages": []}
    msgs = (
        await db.execute(
            select(ConversationMessage)
            .where(ConversationMessage.thread_id == thread.id, ConversationMessage.deleted_at.is_(None))
            .order_by(ConversationMessage.sent_at)
        )
    ).scalars().all()
    return {
        "messages": [
            {"id": str(m.id), "from": m.sender_role.value, "body": m.body, "time": m.sent_at.isoformat(), "orderId": str(m.order_id) if m.order_id else None}
            for m in msgs
        ]
    }


@router.post("/conversations/miu-account-manager/messages")
async def buyer_send_message(
    data: MessageBodyRequest,
    db: AsyncSession = Depends(get_db),
    org_id: UUID = Depends(require_onboarded_buyer_org_id),
    account: BuyerAccount = Depends(require_buyer_password_changed),
):
    from datetime import datetime, timezone
    from app.models.enums import ConversationType, SenderRole
    from app.models.messaging import ConversationMessage, ConversationThread
    thread = (
        await db.execute(select(ConversationThread).where(ConversationThread.buyer_org_id == org_id, ConversationThread.thread_type == ConversationType.BUYER_MIU))
    ).scalar_one_or_none()
    if not thread:
        thread = ConversationThread(thread_type=ConversationType.BUYER_MIU, buyer_org_id=org_id, subject="MIU Account Manager")
        apply_create_audit(thread, account.id)
        db.add(thread)
        await db.flush()
    msg = ConversationMessage(thread_id=thread.id, sender_role=SenderRole.BUYER, body=data.body, sent_at=datetime.now(timezone.utc))
    apply_create_audit(msg, account.id)
    db.add(msg)
    return {"ok": True}


@router.get("/notifications/summary")
async def buyer_notif_summary(db: AsyncSession = Depends(get_db), account: BuyerAccount = Depends(require_buyer_password_changed)):
    unread = (
        await db.execute(
            select(BuyerNotification).where(
                BuyerNotification.buyer_account_id == account.id,
                BuyerNotification.read_at.is_(None),
                BuyerNotification.deleted_at.is_(None),
            )
        )
    ).scalars().all()
    rfq_count = sum(1 for n in unread if n.type == "rfq")
    msg_count = sum(1 for n in unread if n.type == "message")
    return {"rfqs": rfq_count, "messages": msg_count}


@router.get("/search")
async def buyer_search(
    q: str = Query(...),
    db: AsyncSession = Depends(get_db),
    org: BuyerOrganization = Depends(get_buyer_org),
    _: BuyerAccount = Depends(require_buyer_password_changed),
):
    browse = await CatalogService.buyer_browse(db, q=q, customer_type=org.industry)
    return {"query": q, "destinations": {"products": browse["products"][:5], "browse": "/dashboard/buyer/browse"}}


@router.get("/settings/preferences")
async def get_preferences(db: AsyncSession = Depends(get_db), account: BuyerAccount = Depends(require_buyer_password_changed)):
    pref = (await db.execute(select(BuyerPreference).where(BuyerPreference.buyer_account_id == account.id))).scalar_one_or_none()
    return {"language": pref.language if pref else "en", "timezone": pref.timezone if pref else "UTC", "currency": pref.currency_display if pref else "UGX"}


@router.put("/settings/preferences")
async def put_preferences(data: dict, db: AsyncSession = Depends(get_db), account: BuyerAccount = Depends(require_buyer_password_changed)):
    pref = (await db.execute(select(BuyerPreference).where(BuyerPreference.buyer_account_id == account.id))).scalar_one_or_none()
    if not pref:
        pref = BuyerPreference(buyer_account_id=account.id, language=data.get("language", "en"), timezone=data.get("timezone", "UTC"), currency_display=data.get("currency", "UGX"))
        apply_create_audit(pref, account.id)
        db.add(pref)
    else:
        pref.language = data.get("language", pref.language)
        pref.timezone = data.get("timezone", pref.timezone)
        pref.currency_display = data.get("currency", pref.currency_display)
    return {"ok": True}


@router.get("/settings/sessions")
async def list_sessions(db: AsyncSession = Depends(get_db), account: BuyerAccount = Depends(require_buyer_password_changed)):
    sessions = (
        await db.execute(
            select(BuyerSession).where(
                BuyerSession.buyer_account_id == account.id, BuyerSession.revoked_at.is_(None)
            )
        )
    ).scalars().all()
    return {"items": [{"id": str(s.id), "userAgent": s.user_agent, "ip": s.ip_address, "expiresAt": s.expires_at.isoformat()} for s in sessions]}


@router.delete("/settings/sessions/{session_id}")
async def revoke_session(session_id: UUID, db: AsyncSession = Depends(get_db), account: BuyerAccount = Depends(require_buyer_password_changed)):
    from datetime import datetime, timezone
    s = await db.get(BuyerSession, session_id)
    if s and s.buyer_account_id == account.id:
        s.revoked_at = datetime.now(timezone.utc)
    return {"ok": True}


@router.get("/settings/notifications")
async def get_notif_settings(db: AsyncSession = Depends(get_db), account: BuyerAccount = Depends(require_buyer_password_changed)):
    rows = (
        await db.execute(
            select(BuyerNotificationSetting).where(BuyerNotificationSetting.buyer_account_id == account.id)
        )
    ).scalars().all()
    return {"items": [{"channel": r.channel, "eventType": r.event_type, "enabled": r.enabled} for r in rows]}


@router.put("/settings/security/2fa")
async def toggle_2fa(enabled: bool = False, account: BuyerAccount = Depends(require_buyer_password_changed), db: AsyncSession = Depends(get_db)):
    account.two_factor_enabled = enabled
    return {"twoFactorEnabled": enabled}


@router.get("/settings/addresses")
async def list_addresses(db: AsyncSession = Depends(get_db), account: BuyerAccount = Depends(require_buyer_password_changed)):
    rows = (
        await db.execute(
            select(BuyerAddress).where(
                BuyerAddress.buyer_account_id == account.id, BuyerAddress.deleted_at.is_(None)
            )
        )
    ).scalars().all()
    return {"items": [{"id": str(a.id), "label": a.label, "line1": a.line1, "city": a.city, "country": a.country, "postalCode": a.postal_code, "isDefault": a.is_default_delivery} for a in rows]}
