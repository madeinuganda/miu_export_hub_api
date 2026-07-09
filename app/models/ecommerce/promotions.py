from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy import Boolean, Date, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.shared.database import Base
from app.models.shared.base import AuditMixin
from app.models.shared.db_types import str_enum
from app.models.shared.enums import EcommerceCouponType, EcommerceDiscountType


class EcommerceCoupon(AuditMixin, Base):
    __tablename__ = "ecommerce_coupons"

    title: Mapped[str] = mapped_column(String(128), nullable=False)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    coupon_type: Mapped[EcommerceCouponType] = mapped_column(
        str_enum(EcommerceCouponType, name="ecommerce_coupon_type"),
        default=EcommerceCouponType.DISCOUNT_ON_PURCHASE,
        nullable=False,
    )
    discount_type: Mapped[EcommerceDiscountType] = mapped_column(
        str_enum(EcommerceDiscountType, name="ecommerce_coupon_discount_type"),
        default=EcommerceDiscountType.PERCENT,
        nullable=False,
    )
    discount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    max_discount: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2), nullable=True)
    min_purchase: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"), nullable=False)
    shop_id: Mapped[Optional[UUID]] = mapped_column(PGUUID(as_uuid=True), nullable=True, index=True)
    customer_id: Mapped[Optional[UUID]] = mapped_column(PGUUID(as_uuid=True), nullable=True, index=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    expire_date: Mapped[date] = mapped_column(Date, nullable=False)
    usage_limit: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    total_limit: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class EcommerceCouponUsage(AuditMixin, Base):
    __tablename__ = "ecommerce_coupon_usages"
    __table_args__ = (
        UniqueConstraint("coupon_id", "customer_id", "order_group_id", name="uq_ecommerce_coupon_usage"),
    )

    coupon_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    customer_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    order_group_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
