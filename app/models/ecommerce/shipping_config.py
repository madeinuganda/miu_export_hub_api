from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import Boolean, Numeric, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.shared.database import Base
from app.models.shared.base import AuditMixin


class EcommerceShopShippingMethod(AuditMixin, Base):
    __tablename__ = "ecommerce_shop_shipping_methods"

    shop_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(128), nullable=False)
    duration: Mapped[str] = mapped_column(String(64), default="2-5 business days", nullable=False)
    cost: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="UGX", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(default=0, nullable=False)
