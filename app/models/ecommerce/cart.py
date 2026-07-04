from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import Boolean, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.shared.database import Base
from app.models.shared.base import AuditMixin
from app.models.shared.db_types import str_enum
from app.models.shared.enums import EcommerceDiscountType


class EcommerceCartItem(AuditMixin, Base):
    """Cart line — owned by a guest (EcommerceGuest.id) or customer (CustomerAccount.id)."""

    __tablename__ = "ecommerce_cart_items"
    __table_args__ = (
        UniqueConstraint("owner_id", "is_guest", "product_id", name="uq_ecommerce_cart_owner_product"),
    )

    owner_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    is_guest: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    cart_group_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    shop_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    product_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    discount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"), nullable=False)
    discount_type: Mapped[EcommerceDiscountType] = mapped_column(
        str_enum(EcommerceDiscountType, name="ecommerce_cart_discount_type"),
        default=EcommerceDiscountType.PERCENT,
        nullable=False,
    )
    is_checked: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    product_name: Mapped[str] = mapped_column(String(512), nullable=False)
    product_slug: Mapped[str] = mapped_column(String(256), nullable=False)
    product_thumbnail: Mapped[str | None] = mapped_column(String(512), nullable=True)
