from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy import Boolean, Date, DateTime, Enum, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.shared.base import AuditMixin
from app.models.shared.enums import MilestoneState, OrderStatus
from app.core.shared.database import Base


class Order(AuditMixin, Base):
    __tablename__ = "orders"

    public_id: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    buyer_org_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    supplier_org_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    product_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    rfq_id: Mapped[Optional[UUID]] = mapped_column(PGUUID(as_uuid=True), nullable=True, index=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    total_value_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="UGX", nullable=False)
    status: Mapped[OrderStatus] = mapped_column(Enum(OrderStatus, name="order_status"), nullable=False)
    tone: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)


class OrderMilestone(AuditMixin, Base):
    __tablename__ = "order_milestones"

    order_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    step_key: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[str] = mapped_column(String(128), nullable=False)
    state: Mapped[MilestoneState] = mapped_column(Enum(MilestoneState, name="milestone_state"), nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    sort_order: Mapped[int] = mapped_column(default=0, nullable=False)


class OrderActivity(AuditMixin, Base):
    __tablename__ = "order_activity"

    order_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)


class OrderTracking(AuditMixin, Base):
    __tablename__ = "order_tracking"

    order_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    tracking_number: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    carrier: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    eta_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    track_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)


class OrderDocument(AuditMixin, Base):
    __tablename__ = "order_documents"

    order_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    doc_type: Mapped[str] = mapped_column(String(64), nullable=False)
    file_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)


class OrderPaymentProof(AuditMixin, Base):
    """An admin-recorded payment against an order (down payment, progressive
    payment, completion). An order can carry many.

    ``file_id`` holds a manually attached receipt; when absent MIU generates a
    receipt PDF on demand. ``send_attachment`` controls whether the document is
    attached to the notification emails.
    """

    __tablename__ = "order_payment_proofs"

    order_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    reference_no: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    payment_type: Mapped[str] = mapped_column(String(32), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="UGX", nullable=False)
    method: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    payment_reference: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    paid_at: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    file_id: Mapped[Optional[UUID]] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    file_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    send_attachment: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notify_buyer: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notify_supplier: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
