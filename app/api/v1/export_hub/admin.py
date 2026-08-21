from __future__ import annotations

from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.shared.config import get_settings
from app.core.shared.database import get_db
from app.core.export_hub.deps import require_admin_password_changed
from app.core.shared.rbac_deps import require_export_hub_permission
from app.core.shared.exceptions import AppError
from app.models.export_hub.accounts import AdminAccount
from app.models.export_hub.misc import FileRecord
from app.schemas.export_hub.catalog import CategoryCreate, CategoryItem, CategoryListResponse, CategoryUpdate
from app.schemas.export_hub.admin import (
    AdminDealListResponse,
    AdminMessageRequest,
    AdminMessageRevertRequest,
    AdminMessageRouteRequest,
    AdminNotificationsSummary,
    AdminOrderListResponse,
    AdminProductFeaturedUpdate,
    AdminProductListItem,
    AdminProductListResponse,
    AdminRfqListResponse,
    EscrowReleaseResponse,
    OrderAdvanceRequest,
    OrderMilestoneUpdateRequest,
    OrderMilestoneUpdateResponse,
    OrderPipelineStepsResponse,
    RelayQuoteRequest,
    RfqAssignRequest,
    BuyerAdminItem,
    BuyerAdminListResponse,
    VerificationApplicationsResponse,
    VerificationApplicationItem,
    VerificationDocumentsBulkBody,
    VerificationRequestInfoBody,
    VerifyRequest,
)
from app.schemas.export_hub.auth import AdminInviteRequest, AdminInviteResponse
from app.services.export_hub.admin_auth_service import AdminAuthService
from app.services.export_hub.admin_service import AdminService
from app.services.export_hub.category_service import CategoryService
from app.services.export_hub.product_admin_service import ProductAdminService
from app.services.export_hub.testimonial_service import TestimonialService
from app.services.export_hub.browse_service import BrowseService
from app.models.export_hub.organizations import SupplierOrganization
from app.models.export_hub.catalog import Product
from app.schemas.export_hub.browse import BrowseSettingsItem, BrowseSettingsUpdate, FeaturedFlagUpdate, TopDealUpdate
from app.schemas.export_hub.testimonial import (
    TestimonialCreate,
    TestimonialItem,
    TestimonialListResponse,
    TestimonialUpdate,
)

router = APIRouter(prefix="/admin")


@router.get("/notifications/summary", response_model=AdminNotificationsSummary)
async def notifications_summary(
    db: AsyncSession = Depends(get_db),
    _: AdminAccount = Depends(require_admin_password_changed),
):
    from app.services.export_hub.nav_badges_service import NavBadgesService

    return await NavBadgesService.admin_badges(db)


@router.get("/rfqs", response_model=AdminRfqListResponse)
async def list_rfqs(
    status: str | None = Query(None, description="new | routed | responded | closed"),
    q: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: AdminAccount = Depends(require_admin_password_changed),
):
    return await AdminService.list_rfqs(db, status=status, q=q, page=page, page_size=page_size)


@router.get("/rfqs/{public_id}")
async def get_rfq(
    public_id: str,
    db: AsyncSession = Depends(get_db),
    _: AdminAccount = Depends(require_admin_password_changed),
):
    return await AdminService.get_rfq_detail(db, public_id)


@router.post("/rfqs/{public_id}/assign")
async def assign_rfq(
    public_id: str,
    data: RfqAssignRequest,
    db: AsyncSession = Depends(get_db),
    admin: AdminAccount = Depends(require_admin_password_changed),
):
    return await AdminService.assign_rfq(db, admin, public_id, data)


@router.post("/rfqs/{public_id}/relay-quote")
async def relay_quote(
    public_id: str,
    data: RelayQuoteRequest,
    db: AsyncSession = Depends(get_db),
    admin: AdminAccount = Depends(require_admin_password_changed),
):
    return await AdminService.relay_quote(db, admin, public_id, data)


@router.get("/rfqs/{public_id}/messages")
@router.get("/deals/{public_id}/messages")
async def admin_thread_messages(
    public_id: str,
    db: AsyncSession = Depends(get_db),
    _: AdminAccount = Depends(require_admin_password_changed),
):
    """Full unfiltered deal thread (works for both an RFQ-... and DEAL-... id,
    since a deal's thread is the same underlying RFQ thread)."""
    return await AdminService.list_thread_messages(db, public_id)


@router.post("/rfqs/{public_id}/messages")
@router.post("/deals/{public_id}/messages")
async def admin_send_thread_message(
    public_id: str,
    data: AdminMessageRequest,
    db: AsyncSession = Depends(get_db),
    admin: AdminAccount = Depends(require_admin_password_changed),
):
    """Admin posts directly into the thread — visible to both sides right away."""
    return await AdminService.send_relay_message(db, admin, public_id, data.body)


@router.post("/rfqs/{public_id}/messages/{message_id}/route")
@router.post("/deals/{public_id}/messages/{message_id}/route")
async def admin_route_message(
    public_id: str,
    message_id: UUID,
    data: AdminMessageRouteRequest,
    db: AsyncSession = Depends(get_db),
    admin: AdminAccount = Depends(require_admin_password_changed),
):
    """Deliver a pending buyer/supplier message to the other party."""
    return await AdminService.route_message(db, admin, public_id, message_id, data.note)


@router.post("/rfqs/{public_id}/messages/{message_id}/revert")
@router.post("/deals/{public_id}/messages/{message_id}/revert")
async def admin_revert_message(
    public_id: str,
    message_id: UUID,
    data: AdminMessageRevertRequest,
    db: AsyncSession = Depends(get_db),
    admin: AdminAccount = Depends(require_admin_password_changed),
):
    """Bounce a pending message back to its sender with remarks; never delivered."""
    return await AdminService.revert_message(db, admin, public_id, message_id, data.remarks)


@router.get("/deals", response_model=AdminDealListResponse)
async def list_deals(
    status: str | None = Query(None, description="active | quote_sent | accepted | order_created | completed | all"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: AdminAccount = Depends(require_admin_password_changed),
):
    return await AdminService.list_deals(db, status=status, page=page, page_size=page_size)


@router.get("/deals/{public_id}")
async def get_deal(
    public_id: str,
    db: AsyncSession = Depends(get_db),
    _: AdminAccount = Depends(require_admin_password_changed),
):
    return await AdminService.get_deal_detail(db, public_id)


@router.get("/orders/pipeline-stages", response_model=OrderPipelineStepsResponse)
async def order_pipeline_stages(
    _: AdminAccount = Depends(require_admin_password_changed),
):
    """Seven admin order stages from Confirmed through Fulfilled."""
    return OrderPipelineStepsResponse(stages=AdminService.pipeline_stages())


@router.get("/orders", response_model=AdminOrderListResponse)
async def list_orders(
    stage: str | None = Query(None, description="Pipeline stage filter"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: AdminAccount = Depends(require_admin_password_changed),
):
    return await AdminService.list_orders(db, stage=stage, page=page, page_size=page_size)


@router.get("/orders/{public_id}")
async def get_order(
    public_id: str,
    db: AsyncSession = Depends(get_db),
    _: AdminAccount = Depends(require_admin_password_changed),
):
    return await AdminService.get_order_detail(db, public_id)


@router.post("/orders/{public_id}/advance", response_model=OrderMilestoneUpdateResponse)
async def advance_order(
    public_id: str,
    data: OrderAdvanceRequest | None = None,
    db: AsyncSession = Depends(get_db),
    admin: AdminAccount = Depends(require_admin_password_changed),
):
    """
    Advance the order by one pipeline step (Confirmed → Payment Secured → … → Fulfilled).
    Optional carrier/tracking_number when moving into Shipped.
    """
    body = data or OrderAdvanceRequest()
    return await AdminService.advance_order(
        db,
        admin,
        public_id,
        carrier=body.carrier,
        tracking_number=body.tracking_number,
    )


@router.put("/orders/{public_id}/milestones", response_model=OrderMilestoneUpdateResponse)
async def update_milestones(
    public_id: str,
    data: OrderMilestoneUpdateRequest,
    db: AsyncSession = Depends(get_db),
    admin: AdminAccount = Depends(require_admin_password_changed),
):
    """
    Set order to a specific pipeline stage. By default only the next stage is allowed;
    pass admin_override=true to jump stages.
    """
    return await AdminService.update_order_milestones(
        db,
        admin,
        public_id,
        pipeline_stage=data.pipeline_stage,
        carrier=data.carrier,
        tracking_number=data.tracking_number,
        admin_override=data.admin_override,
    )


@router.post("/orders/{public_id}/escrow/release", response_model=EscrowReleaseResponse)
async def release_escrow(
    public_id: str,
    db: AsyncSession = Depends(get_db),
    admin: AdminAccount = Depends(require_admin_password_changed),
):
    return await AdminService.release_escrow(db, admin, public_id)


@router.get("/verification/applications", response_model=VerificationApplicationsResponse)
async def list_verification_applications(
    status: str | None = Query(None, description="pending | approved | rejected | processed | all"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: AdminAccount = Depends(require_admin_password_changed),
):
    return await AdminService.list_verification_applications(db, status=status, page=page, page_size=page_size)


@router.get("/verification/applications/{application_id}", response_model=VerificationApplicationItem)
async def get_verification_application(
    application_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: AdminAccount = Depends(require_admin_password_changed),
):
    return await AdminService.get_verification_application(db, application_id)


@router.post("/verification/applications/{application_id}/request-info")
async def request_verification_info(
    application_id: UUID,
    data: VerificationRequestInfoBody | None = None,
    db: AsyncSession = Depends(get_db),
    admin: AdminAccount = Depends(require_admin_password_changed),
):
    body = data or VerificationRequestInfoBody()
    return await AdminService.request_verification_info(db, admin, application_id, body.message)


@router.post("/verification/applications/{application_id}/suspend")
async def suspend_verification_application(
    application_id: UUID,
    data: VerificationRequestInfoBody | None = None,
    db: AsyncSession = Depends(get_db),
    admin: AdminAccount = Depends(require_admin_password_changed),
):
    body = data or VerificationRequestInfoBody()
    return await AdminService.suspend_supplier(db, admin, application_id, body.message)


@router.post("/verification/applications/{application_id}/restore")
async def restore_verification_application(
    application_id: UUID,
    data: VerificationRequestInfoBody | None = None,
    db: AsyncSession = Depends(get_db),
    admin: AdminAccount = Depends(require_admin_password_changed),
):
    body = data or VerificationRequestInfoBody()
    return await AdminService.restore_supplier(db, admin, application_id, body.message)


@router.post("/verification/documents/{doc_id}/approve")
async def approve_verification_document(
    doc_id: UUID,
    data: VerificationRequestInfoBody | None = None,
    db: AsyncSession = Depends(get_db),
    admin: AdminAccount = Depends(require_admin_password_changed),
):
    body = data or VerificationRequestInfoBody()
    return await AdminService.approve_verification_document(db, admin, doc_id, body.message)


@router.post("/verification/documents/{doc_id}/reject")
async def reject_verification_document(
    doc_id: UUID,
    data: VerificationRequestInfoBody | None = None,
    db: AsyncSession = Depends(get_db),
    admin: AdminAccount = Depends(require_admin_password_changed),
):
    body = data or VerificationRequestInfoBody()
    return await AdminService.reject_verification_document(db, admin, doc_id, body.message)


@router.post("/verification/documents/{doc_id}/flag")
async def flag_verification_document(
    doc_id: UUID,
    data: VerificationRequestInfoBody | None = None,
    db: AsyncSession = Depends(get_db),
    admin: AdminAccount = Depends(require_admin_password_changed),
):
    body = data or VerificationRequestInfoBody()
    return await AdminService.flag_verification_document(db, admin, doc_id, body.message)


@router.post("/verification/applications/{application_id}/documents/bulk")
async def bulk_update_verification_documents(
    application_id: UUID,
    data: VerificationDocumentsBulkBody,
    db: AsyncSession = Depends(get_db),
    admin: AdminAccount = Depends(require_admin_password_changed),
):
    return await AdminService.bulk_update_verification_documents(
        db,
        admin,
        application_id,
        action=data.action,
        document_ids=data.document_ids,
        message=data.message,
    )


@router.delete("/verification/documents/{doc_id}")
async def delete_verification_document(
    doc_id: UUID,
    hard: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    admin: AdminAccount = Depends(require_admin_password_changed),
):
    return await AdminService.delete_verification_document(db, admin, doc_id, hard=hard)


@router.get("/files/{file_id}")
async def download_verification_file(
    file_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: AdminAccount = Depends(require_admin_password_changed),
):
    record = await db.get(FileRecord, file_id)
    if not record or record.deleted_at:
        raise AppError(404, "File not found", "not_found")

    path = Path(get_settings().storage_path) / record.storage_key
    if not path.is_file():
        raise AppError(404, "File not found on disk", "not_found")

    download_name = Path(record.storage_key).name
    return FileResponse(
        path,
        media_type=record.mime_type,
        filename=download_name,
        content_disposition_type="inline",
    )


@router.delete("/files/{file_id}")
async def delete_file_record(
    file_id: UUID,
    hard: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    admin: AdminAccount = Depends(require_admin_password_changed),
):
    return await AdminService.delete_file_record(db, admin, file_id, hard=hard)


@router.post("/invites", response_model=AdminInviteResponse)
async def invite_admin(
    data: AdminInviteRequest,
    db: AsyncSession = Depends(get_db),
    admin: AdminAccount = Depends(require_export_hub_permission("export_hub.admins.manage")),
):
    return await AdminAuthService.invite(db, admin, data)


@router.post("/suppliers/{org_id}/verify")
async def verify_supplier(
    org_id: UUID,
    data: VerifyRequest,
    db: AsyncSession = Depends(get_db),
    admin: AdminAccount = Depends(require_admin_password_changed),
):
    return await AdminService.verify_supplier(db, admin, org_id, data)


@router.delete("/suppliers/{org_id}")
async def delete_supplier(
    org_id: UUID,
    hard: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    admin: AdminAccount = Depends(require_admin_password_changed),
):
    return await AdminService.delete_supplier_org(db, admin, org_id, hard=hard)


@router.get("/buyers", response_model=BuyerAdminListResponse)
async def list_buyers(
    status: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: AdminAccount = Depends(require_admin_password_changed),
):
    return await AdminService.list_buyers(db, status=status, page=page, page_size=page_size)


@router.get("/buyers/{org_id}", response_model=BuyerAdminItem)
async def get_buyer(
    org_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: AdminAccount = Depends(require_admin_password_changed),
):
    return await AdminService.get_buyer_detail(db, org_id)


@router.post("/buyers/{org_id}/verify")
async def verify_buyer(
    org_id: UUID,
    data: VerifyRequest,
    db: AsyncSession = Depends(get_db),
    admin: AdminAccount = Depends(require_admin_password_changed),
):
    return await AdminService.verify_buyer(db, admin, org_id, data)


@router.post("/buyers/{org_id}/request-info")
async def request_buyer_info(
    org_id: UUID,
    data: VerificationRequestInfoBody,
    db: AsyncSession = Depends(get_db),
    admin: AdminAccount = Depends(require_admin_password_changed),
):
    return await AdminService.request_buyer_info(db, admin, org_id, data.message)


@router.post("/buyers/{org_id}/suspend")
async def suspend_buyer(
    org_id: UUID,
    data: VerificationRequestInfoBody,
    db: AsyncSession = Depends(get_db),
    admin: AdminAccount = Depends(require_admin_password_changed),
):
    return await AdminService.suspend_buyer(db, admin, org_id, data.message)


@router.post("/buyers/{org_id}/restore")
async def restore_buyer(
    org_id: UUID,
    data: VerificationRequestInfoBody,
    db: AsyncSession = Depends(get_db),
    admin: AdminAccount = Depends(require_admin_password_changed),
):
    return await AdminService.restore_buyer(db, admin, org_id, data.message)


@router.delete("/buyers/{org_id}")
async def delete_buyer(
    org_id: UUID,
    hard: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    admin: AdminAccount = Depends(require_admin_password_changed),
):
    return await AdminService.delete_buyer_org(db, admin, org_id, hard=hard)


@router.get("/categories", response_model=CategoryListResponse)
async def list_categories(
    active_only: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    _: AdminAccount = Depends(require_admin_password_changed),
):
    return await CategoryService.list_categories(db, active_only=active_only)


@router.get("/categories/{category_id}", response_model=CategoryItem)
async def get_category(
    category_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: AdminAccount = Depends(require_admin_password_changed),
):
    return await CategoryService.get_category(db, category_id)


@router.post("/categories", response_model=CategoryItem, status_code=201)
async def create_category(
    data: CategoryCreate,
    db: AsyncSession = Depends(get_db),
    admin: AdminAccount = Depends(require_admin_password_changed),
):
    return await CategoryService.create_category(db, admin, data)


@router.patch("/categories/{category_id}", response_model=CategoryItem)
async def update_category(
    category_id: UUID,
    data: CategoryUpdate,
    db: AsyncSession = Depends(get_db),
    admin: AdminAccount = Depends(require_admin_password_changed),
):
    return await CategoryService.update_category(db, admin, category_id, data)


@router.post("/categories/{category_id}/image", response_model=CategoryItem)
async def upload_category_image(
    category_id: UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    admin: AdminAccount = Depends(require_admin_password_changed),
):
    return await CategoryService.upload_category_image(db, admin, category_id, file, kind="image")


@router.post("/categories/{category_id}/thumb", response_model=CategoryItem)
async def upload_category_thumb(
    category_id: UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    admin: AdminAccount = Depends(require_admin_password_changed),
):
    return await CategoryService.upload_category_image(db, admin, category_id, file, kind="thumb")


@router.delete("/categories/{category_id}")
async def delete_category(
    category_id: UUID,
    hard: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    admin: AdminAccount = Depends(require_admin_password_changed),
):
    return await CategoryService.delete_category(db, admin, category_id, hard=hard)


@router.get("/testimonials", response_model=TestimonialListResponse)
async def list_testimonials(
    active_only: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    _: AdminAccount = Depends(require_admin_password_changed),
):
    return await TestimonialService.list_testimonials(db, active_only=active_only)


@router.get("/testimonials/{testimonial_id}", response_model=TestimonialItem)
async def get_testimonial(
    testimonial_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: AdminAccount = Depends(require_admin_password_changed),
):
    return await TestimonialService.get_testimonial(db, testimonial_id)


@router.post("/testimonials", response_model=TestimonialItem, status_code=201)
async def create_testimonial(
    data: TestimonialCreate,
    db: AsyncSession = Depends(get_db),
    admin: AdminAccount = Depends(require_admin_password_changed),
):
    return await TestimonialService.create_testimonial(db, admin, data)


@router.patch("/testimonials/{testimonial_id}", response_model=TestimonialItem)
async def update_testimonial(
    testimonial_id: UUID,
    data: TestimonialUpdate,
    db: AsyncSession = Depends(get_db),
    admin: AdminAccount = Depends(require_admin_password_changed),
):
    return await TestimonialService.update_testimonial(db, admin, testimonial_id, data)


@router.post("/testimonials/{testimonial_id}/avatar", response_model=TestimonialItem)
async def upload_testimonial_avatar(
    testimonial_id: UUID,
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    admin: AdminAccount = Depends(require_admin_password_changed),
):
    return await TestimonialService.upload_avatar(db, admin, testimonial_id, file)


@router.delete("/testimonials/{testimonial_id}")
async def delete_testimonial(
    testimonial_id: UUID,
    hard: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    admin: AdminAccount = Depends(require_admin_password_changed),
):
    return await TestimonialService.delete_testimonial(db, admin, testimonial_id, hard=hard)


@router.get("/browse-settings", response_model=BrowseSettingsItem)
async def get_browse_settings(
    db: AsyncSession = Depends(get_db),
    _: AdminAccount = Depends(require_admin_password_changed),
):
    settings = await BrowseService.get_settings(db)
    return BrowseSettingsItem(
        ranking_rating_weight=settings.ranking_rating_weight,
        ranking_review_weight=settings.ranking_review_weight,
        top_deals_limit=settings.top_deals_limit,
        top_ranking_limit=settings.top_ranking_limit,
        featured_suppliers_limit=settings.featured_suppliers_limit,
        featured_categories_limit=settings.featured_categories_limit,
    )


@router.patch("/browse-settings", response_model=BrowseSettingsItem)
async def update_browse_settings(
    data: BrowseSettingsUpdate,
    db: AsyncSession = Depends(get_db),
    admin: AdminAccount = Depends(require_admin_password_changed),
):
    settings = await BrowseService.get_settings(db)
    updates = data.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(settings, key, value)
    from app.utils.audit import apply_update_audit
    apply_update_audit(settings, admin.id)
    await db.flush()
    return BrowseSettingsItem(
        ranking_rating_weight=settings.ranking_rating_weight,
        ranking_review_weight=settings.ranking_review_weight,
        top_deals_limit=settings.top_deals_limit,
        top_ranking_limit=settings.top_ranking_limit,
        featured_suppliers_limit=settings.featured_suppliers_limit,
        featured_categories_limit=settings.featured_categories_limit,
    )


@router.patch("/categories/{category_id}/featured", response_model=CategoryItem)
async def set_category_featured(
    category_id: UUID,
    data: FeaturedFlagUpdate,
    db: AsyncSession = Depends(get_db),
    admin: AdminAccount = Depends(require_admin_password_changed),
):
    return await CategoryService.update_category(
        db, admin, category_id, CategoryUpdate(featured=data.featured)
    )


@router.patch("/suppliers/{org_id}/featured")
async def set_supplier_featured(
    org_id: UUID,
    data: FeaturedFlagUpdate,
    db: AsyncSession = Depends(get_db),
    admin: AdminAccount = Depends(require_admin_password_changed),
):
    org = await db.get(SupplierOrganization, org_id)
    if not org or org.deleted_at:
        raise AppError(404, "Supplier not found", "not_found")
    org.featured = data.featured
    from app.utils.audit import apply_update_audit
    apply_update_audit(org, admin.id)
    await db.flush()
    return {"ok": True, "id": str(org_id), "featured": org.featured}


@router.patch("/products/{product_id}/top-deal", response_model=AdminProductListItem)
async def set_product_top_deal(
    product_id: UUID,
    data: TopDealUpdate,
    db: AsyncSession = Depends(get_db),
    admin: AdminAccount = Depends(require_admin_password_changed),
):
    product = await db.get(Product, product_id)
    if not product or product.deleted_at:
        raise AppError(404, "Product not found", "not_found")
    product.is_top_deal = data.is_top_deal
    if data.deal_price is not None:
        product.deal_price = data.deal_price
    from app.utils.audit import apply_update_audit
    apply_update_audit(product, admin.id)
    await db.flush()
    return await ProductAdminService._to_item(db, product)


@router.get("/products", response_model=AdminProductListResponse)
async def list_products(
    q: str | None = Query(None),
    status: str | None = Query(None),
    featured: bool | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: AdminAccount = Depends(require_admin_password_changed),
):
    return await ProductAdminService.list_products(
        db,
        q=q,
        status=status,
        featured=featured,
        page=page,
        page_size=page_size,
    )


@router.patch("/products/{product_id}/featured", response_model=AdminProductListItem)
async def set_product_featured(
    product_id: UUID,
    data: AdminProductFeaturedUpdate,
    db: AsyncSession = Depends(get_db),
    admin: AdminAccount = Depends(require_admin_password_changed),
):
    return await ProductAdminService.set_featured(db, admin, product_id, data)


@router.delete("/products/{product_id}")
async def delete_product(
    product_id: UUID,
    hard: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    admin: AdminAccount = Depends(require_admin_password_changed),
):
    return await AdminService.delete_product(db, admin, product_id, hard=hard)


@router.put("/cms/{section}")
async def update_cms(
    section: str,
    data: dict,
    _: AdminAccount = Depends(require_admin_password_changed),
):
    return {"section": section, "updated": True, "stub": True, "payload": data}


@router.post("/cms/reorder")
async def reorder_cms(
    data: dict,
    _: AdminAccount = Depends(require_admin_password_changed),
):
    return {"ok": True, "order": data.get("items", [])}
