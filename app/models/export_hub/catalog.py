from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.shared.base import AuditMixin
from app.models.shared.enums import ProductStatus, StockStatus
from app.core.shared.database import Base


class Category(AuditMixin, Base):
    __tablename__ = "categories"

    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    label: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    parent_id: Mapped[Optional[UUID]] = mapped_column(PGUUID(as_uuid=True), ForeignKey("categories.id"), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    featured: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    image_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    thumb_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)


class Product(AuditMixin, Base):
    __tablename__ = "products"

    supplier_org_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    sku: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    category_id: Mapped[Optional[UUID]] = mapped_column(PGUUID(as_uuid=True), ForeignKey("categories.id"), nullable=True)
    subcategory: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    origin_story: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[ProductStatus] = mapped_column(Enum(ProductStatus, name="product_status"), nullable=False)
    moq_value: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4), nullable=True)
    moq_unit: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    price_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2), nullable=True)
    price_currency: Mapped[str] = mapped_column(String(10), default="UGX", nullable=False)
    lead_time_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    stock_status: Mapped[StockStatus] = mapped_column(Enum(StockStatus, name="stock_status"), nullable=False)
    trade_assurance_note: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    sample_available: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    rating: Mapped[Decimal] = mapped_column(Numeric(3, 2), default=Decimal("5.0"), nullable=False)
    review_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tone: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    featured: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_top_deal: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    deal_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2), nullable=True)
    submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_by: Mapped[Optional[UUID]] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    review_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class ProductImage(AuditMixin, Base):
    __tablename__ = "product_images"

    product_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    url: Mapped[str] = mapped_column(String(512), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class ProductCertification(AuditMixin, Base):
    __tablename__ = "product_certifications"

    product_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    certification_name: Mapped[str] = mapped_column(String(128), nullable=False)


class ProductBadge(AuditMixin, Base):
    __tablename__ = "product_badges"

    product_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    badge: Mapped[str] = mapped_column(String(64), nullable=False)


class PlatformStat(AuditMixin, Base):
    __tablename__ = "platform_stats"

    key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    headline: Mapped[str] = mapped_column(String(128), nullable=False)
    subtext: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    icon_key: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
