from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class VerifyRequest(BaseModel):
    approved: bool
    reason: str | None = None


class AdminNotificationsSummary(BaseModel):
    unread_count: int


class RfqAssignRequest(BaseModel):
    supplier_org_ids: list[UUID] = Field(min_length=1)
    note: str | None = None


class RelayQuoteRequest(BaseModel):
    quote_id: UUID | None = None
    message: str | None = None


class AdminPipelineStage(BaseModel):
    id: str
    label: str
    index: int


class OrderMilestoneUpdateRequest(BaseModel):
    pipeline_stage: str = Field(
        description="One of: confirmed, payment_secured, in_production, ready_to_dispatch, shipped, delivered, fulfilled"
    )
    carrier: str | None = None
    tracking_number: str | None = None
    admin_override: bool = Field(
        default=False,
        description="If true, allow jumping to any stage (not only next)",
    )


class OrderAdvanceRequest(BaseModel):
    carrier: str | None = Field(default=None, description="Set when advancing to shipped")
    tracking_number: str | None = Field(default=None, description="Set when advancing to shipped")


class VerificationRequestInfoBody(BaseModel):
    message: str | None = None


class AdminRfqListItem(BaseModel):
    id: UUID
    public_id: str
    buyer_name: str
    buyer_company: str
    buyer_country: str
    product_name: str
    category: str
    quantity: str
    destination: str
    submitted_at: datetime | None
    status: str
    assigned_admin_name: str | None
    action: str


class AdminRfqListSummary(BaseModel):
    new_count: int
    total: int
    avg_response_hours: float | None
    active_this_week: int


class AdminRfqListResponse(BaseModel):
    summary: AdminRfqListSummary
    items: list[AdminRfqListItem]
    page: int
    page_size: int
    total: int
    pages: int


class AdminDealListItem(BaseModel):
    id: UUID
    public_id: str
    buyer_name: str
    buyer_company: str
    supplier_name: str
    supplier_company: str
    product: str
    value_ugx: int
    value_display: str
    status: str
    last_activity_at: datetime | None
    assigned_admin_name: str | None


class AdminDealListResponse(BaseModel):
    active_deals_count: int
    items: list[AdminDealListItem]
    page: int
    page_size: int
    total: int
    pages: int


class AdminOrderListItem(BaseModel):
    id: UUID
    public_id: str
    product: str
    buyer_name: str
    supplier_name: str
    value_display: str
    order_date: str
    assigned_admin_name: str | None
    pipeline_stage: str
    pipeline_index: int
    payment_status: str
    carrier: str | None = None
    tracking_number: str | None = None


class AdminOrderListSummary(BaseModel):
    total_value_ugx: int
    total_value_display: str


class AdminOrderListResponse(BaseModel):
    summary: AdminOrderListSummary
    items: list[AdminOrderListItem]
    page: int
    page_size: int
    total: int
    pages: int


class VerificationDocumentItem(BaseModel):
    key: str
    label: str
    status: str
    required: bool = True
    has_file: bool = False
    file_id: UUID | None = None
    filename: str | None = None
    mime_type: str | None = None
    file_url: str | None = None


class VerificationApplicationItem(BaseModel):
    id: UUID
    org_id: UUID
    company_name: str
    industry: str
    location: str
    contact_name: str
    email: str
    submitted_at: datetime | None
    hours_elapsed: int
    status: str
    info_requested: bool
    admin_message: str | None = None
    missing_items: list[str] = []
    documents: list[VerificationDocumentItem]


class VerificationApplicationsResponse(BaseModel):
    summary: dict[str, int]
    pending: list[VerificationApplicationItem]
    processed: list[VerificationApplicationItem]
    page: int
    page_size: int
    total: int
    pages: int


class BuyerProfileSectionItem(BaseModel):
    key: str
    label: str
    status: str
    detail: str | None = None
    required: bool = True


class BuyerAdminItem(BaseModel):
    id: UUID
    org_id: UUID
    company_name: str
    industry: str
    location: str
    contact_name: str
    email: str
    phone: str | None = None
    website: str | None = None
    job_title: str | None = None
    submitted_at: datetime | None
    hours_elapsed: int
    status: str
    verified_buyer: bool
    info_requested: bool
    admin_message: str | None = None
    missing_items: list[str] = []
    profile_sections: list[BuyerProfileSectionItem]
    rfq_count: int = 0


class BuyerAdminListResponse(BaseModel):
    summary: dict[str, int]
    pending: list[BuyerAdminItem]
    processed: list[BuyerAdminItem]
    page: int
    page_size: int
    total: int
    pages: int


class OrderPipelineStepsResponse(BaseModel):
    stages: list[AdminPipelineStage]


class OrderMilestoneUpdateResponse(BaseModel):
    order: AdminOrderListItem
    pipeline_stage: str
    pipeline_index: int
    next_stage: str | None = None
    next_stage_label: str | None = None
    can_advance: bool = True


class EscrowReleaseResponse(BaseModel):
    public_id: str
    payment_status: str
    released: bool
