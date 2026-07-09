from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy import Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.shared.database import Base
from app.models.shared.base import AuditMixin


class ExportHubProductReview(AuditMixin, Base):
    __tablename__ = "export_hub_product_reviews"
    __table_args__ = (
        UniqueConstraint("product_id", "buyer_org_id", name="uq_export_hub_product_review"),
    )

    product_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    buyer_org_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    buyer_account_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    order_id: Mapped[Optional[UUID]] = mapped_column(PGUUID(as_uuid=True), nullable=True, index=True)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reviewer_name: Mapped[str] = mapped_column(String(128), nullable=False)
