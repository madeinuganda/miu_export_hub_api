from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy import DateTime, Enum, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.shared.base import AuditMixin
from app.models.shared.enums import EscrowStatus, PaymentMilestoneStatus
from app.core.shared.database import Base


class PaymentEscrow(AuditMixin, Base):
    __tablename__ = "payment_escrows"

    order_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), unique=True, nullable=False, index=True)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="UGX", nullable=False)
    upfront_percent: Mapped[int] = mapped_column(Integer, default=70, nullable=False)
    upfront_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    balance_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    status: Mapped[EscrowStatus] = mapped_column(Enum(EscrowStatus, name="escrow_status"), nullable=False)


class PaymentMilestone(AuditMixin, Base):
    __tablename__ = "payment_milestones"

    escrow_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    milestone_type: Mapped[str] = mapped_column(String(32), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    status: Mapped[PaymentMilestoneStatus] = mapped_column(
        Enum(PaymentMilestoneStatus, name="payment_milestone_status"), nullable=False
    )
    released_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class PaymentLink(AuditMixin, Base):
    __tablename__ = "payment_links"

    escrow_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    token: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
