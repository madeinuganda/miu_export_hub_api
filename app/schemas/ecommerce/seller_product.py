from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.shared.enums import EcommerceDiscountType, EcommerceProductStatus, StockStatus
from app.schemas.ecommerce.admin import slugify


class SellerProductCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=512)
    code: str = Field(min_length=1, max_length=64)
    slug: str | None = None
    category_id: UUID | None = None
    sub_category_id: UUID | None = None
    sub_sub_category_id: UUID | None = None
    brand_id: UUID | None = None
    unit_price: Decimal = Field(gt=0)
    discount: Decimal = Decimal("0")
    discount_type: EcommerceDiscountType = EcommerceDiscountType.PERCENT
    thumbnail_url: str | None = None
    details: str | None = None
    status: EcommerceProductStatus = EcommerceProductStatus.DRAFT
    featured: bool = False
    current_stock: int = Field(default=0, ge=0)
    minimum_order_qty: int = Field(default=1, ge=1)
    stock_status: StockStatus = StockStatus.IN_STOCK


class SellerProductUpdateRequest(BaseModel):
    name: str | None = Field(default=None, max_length=512)
    code: str | None = Field(default=None, max_length=64)
    slug: str | None = None
    category_id: UUID | None = None
    sub_category_id: UUID | None = None
    sub_sub_category_id: UUID | None = None
    brand_id: UUID | None = None
    unit_price: Decimal | None = Field(default=None, gt=0)
    discount: Decimal | None = None
    discount_type: EcommerceDiscountType | None = None
    thumbnail_url: str | None = None
    details: str | None = None
    status: EcommerceProductStatus | None = None
    featured: bool | None = None
    current_stock: int | None = Field(default=None, ge=0)
    minimum_order_qty: int | None = Field(default=None, ge=1)
    stock_status: StockStatus | None = None


class SellerStockUpdateRequest(BaseModel):
    current_stock: int = Field(ge=0)
    stock_status: StockStatus | None = None
