from __future__ import annotations

from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.shared.database import Base
from app.models.shared.base import AuditMixin
from app.models.shared.db_types import str_enum
from app.models.shared.enums import (
    EcommerceBannerResourceType,
    EcommerceCategoryPosition,
    EcommerceDiscountType,
    EcommerceProductStatus,
    StockStatus,
)


class EcommerceGuest(AuditMixin, Base):
    __tablename__ = "ecommerce_guests"


class EcommerceCategory(AuditMixin, Base):
    __tablename__ = "ecommerce_categories"

    name: Mapped[str] = mapped_column(String(128), nullable=False)
    slug: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    icon_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    parent_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("ecommerce_categories.id"), nullable=True, index=True
    )
    position: Mapped[EcommerceCategoryPosition] = mapped_column(
        str_enum(EcommerceCategoryPosition, name="ecommerce_category_position"),
        default=EcommerceCategoryPosition.ROOT,
        nullable=False,
    )
    home_status: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class EcommerceBrand(AuditMixin, Base):
    __tablename__ = "ecommerce_brands"

    name: Mapped[str] = mapped_column(String(128), nullable=False)
    slug: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    image_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class EcommerceProduct(AuditMixin, Base):
    __tablename__ = "ecommerce_products"

    shop_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    slug: Mapped[str] = mapped_column(String(256), unique=True, nullable=False, index=True)
    category_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("ecommerce_categories.id"), nullable=True, index=True
    )
    sub_category_id: Mapped[Optional[UUID]] = mapped_column(PGUUID(as_uuid=True), nullable=True, index=True)
    sub_sub_category_id: Mapped[Optional[UUID]] = mapped_column(PGUUID(as_uuid=True), nullable=True, index=True)
    brand_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("ecommerce_brands.id"), nullable=True, index=True
    )
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    discount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"), nullable=False)
    discount_type: Mapped[EcommerceDiscountType] = mapped_column(
        str_enum(EcommerceDiscountType, name="ecommerce_discount_type"),
        default=EcommerceDiscountType.PERCENT,
        nullable=False,
    )
    thumbnail_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[EcommerceProductStatus] = mapped_column(
        str_enum(EcommerceProductStatus, name="ecommerce_product_status"),
        default=EcommerceProductStatus.DRAFT,
        nullable=False,
    )
    featured: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    current_stock: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    minimum_order_qty: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    stock_status: Mapped[StockStatus] = mapped_column(
        str_enum(StockStatus, name="ecommerce_stock_status"),
        default=StockStatus.IN_STOCK,
        nullable=False,
    )
    average_review: Mapped[Decimal] = mapped_column(Numeric(3, 2), default=Decimal("0"), nullable=False)
    reviews_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class EcommerceProductImage(AuditMixin, Base):
    __tablename__ = "ecommerce_product_images"

    product_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    url: Mapped[str] = mapped_column(String(512), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class EcommerceBanner(AuditMixin, Base):
    __tablename__ = "ecommerce_banners"

    title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    sub_title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    button_text: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    photo_url: Mapped[str] = mapped_column(String(512), nullable=False)
    background_color: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    resource_type: Mapped[EcommerceBannerResourceType] = mapped_column(
        str_enum(EcommerceBannerResourceType, name="ecommerce_banner_resource_type"),
        default=EcommerceBannerResourceType.URL,
        nullable=False,
    )
    resource_id: Mapped[Optional[UUID]] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    is_published: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
