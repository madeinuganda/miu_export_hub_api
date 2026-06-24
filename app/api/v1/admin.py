from __future__ import annotations

from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.dependencies import require_admin_password_changed
from app.core.exceptions import AppError
from app.models.accounts import AdminAccount
from app.models.misc import FileRecord
from app.schemas.catalog import CategoryCreate, CategoryItem, CategoryListResponse, CategoryUpdate
from app.schemas.admin import (
    AdminDealListResponse,
    AdminNotificationsSummary,
    AdminOrderListResponse,
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
    VerificationRequestInfoBody,
    VerifyRequest,
)
from app.schemas.auth import AdminInviteRequest, AdminInviteResponse
from app.services.admin_auth_service import AdminAuthService
from app.services.admin_service import AdminService
from app.services.category_service import CategoryService

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/notifications/summary", response_model=AdminNotificationsSummary)
async def notifications_summary(
    db: AsyncSession = Depends(get_db),
    _: AdminAccount = Depends(require_admin_password_changed),
):
    return await AdminService.notifications_summary(db)


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
    admin: AdminAccount = Depends(require_admin_password_changed),
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


@router.delete("/categories/{category_id}")
async def delete_category(
    category_id: UUID,
    hard: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    admin: AdminAccount = Depends(require_admin_password_changed),
):
    return await CategoryService.delete_category(db, admin, category_id, hard=hard)


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
