from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy import Boolean, Date, DateTime, Enum, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import AuditMixin
from app.models.enums import QuoteStatus, RfqStatus, SenderRole
from app.core.database import Base


class Rfq(AuditMixin, Base):
    __tablename__ = "rfqs"

    public_id: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    buyer_org_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    product_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    supplier_org_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    target_price_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2), nullable=True)
    target_price_currency: Mapped[str] = mapped_column(String(10), default="UGX", nullable=False)
    incoterm: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    destination_port: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    required_by_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[RfqStatus] = mapped_column(Enum(RfqStatus, name="rfq_status"), nullable=False)
    sample_requested: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class RfqQuote(AuditMixin, Base):
    __tablename__ = "rfq_quotes"

    rfq_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    supplier_org_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="UGX", nullable=False)
    incoterm: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    lead_time_days: Mapped[Optional[int]] = mapped_column(nullable=True)
    shipment_terms: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[QuoteStatus] = mapped_column(Enum(QuoteStatus, name="quote_status"), nullable=False)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class RfqMessage(AuditMixin, Base):
    __tablename__ = "rfq_messages"

    rfq_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    sender_role: Mapped[SenderRole] = mapped_column(Enum(SenderRole, name="rfq_sender_role"), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
