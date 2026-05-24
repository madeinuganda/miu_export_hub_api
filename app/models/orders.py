from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy import Date, DateTime, Enum, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import AuditMixin
from app.models.enums import MilestoneState, OrderStatus
from app.core.database import Base


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
