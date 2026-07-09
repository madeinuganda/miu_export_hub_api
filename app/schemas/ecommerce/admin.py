from __future__ import annotations

import re
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from app.models.shared.enums import (
    EcommerceBannerResourceType,
    EcommerceCategoryPosition,
    EcommerceCouponType,
    EcommerceDiscountType,
    EcommerceProductStatus,
    StockStatus,
)


def slugify(value: str) -> str:
    slug = re.sub(r"[^\w\s-]", "", value.lower())
    slug = re.sub(r"[\s_-]+", "-", slug).strip("-")
    return slug[:256] or "item"


class CategoryCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    slug: str | None = Field(default=None, max_length=128)
    icon_url: str | None = None
    parent_id: UUID | None = None
    position: EcommerceCategoryPosition = EcommerceCategoryPosition.ROOT
    home_status: bool = True
    priority: int = 0
    is_active: bool = True


class CategoryUpdateRequest(BaseModel):
    name: str | None = Field(default=None, max_length=128)
    slug: str | None = Field(default=None, max_length=128)
    icon_url: str | None = None
    parent_id: UUID | None = None
    home_status: bool | None = None
    priority: int | None = None
    is_active: bool | None = None


class BrandCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    slug: str | None = None
    image_url: str | None = None
    is_active: bool = True


class BrandUpdateRequest(BaseModel):
    name: str | None = Field(default=None, max_length=128)
    slug: str | None = None
    image_url: str | None = None
    is_active: bool | None = None


class AdminProductCreateRequest(BaseModel):
    shop_id: UUID
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


class AdminProductUpdateRequest(BaseModel):
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


class BannerCreateRequest(BaseModel):
    title: str | None = None
    sub_title: str | None = None
    button_text: str | None = None
    photo_url: str
    background_color: str | None = None
    url: str | None = None
    resource_type: EcommerceBannerResourceType = EcommerceBannerResourceType.URL
    resource_id: UUID | None = None
    is_published: bool = True
    sort_order: int = 0


class BannerUpdateRequest(BaseModel):
    title: str | None = None
    sub_title: str | None = None
    button_text: str | None = None
    photo_url: str | None = None
    background_color: str | None = None
    url: str | None = None
    resource_type: EcommerceBannerResourceType | None = None
    resource_id: UUID | None = None
    is_published: bool | None = None
    sort_order: int | None = None


class CouponCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=128)
    code: str = Field(min_length=3, max_length=32)
    coupon_type: EcommerceCouponType = EcommerceCouponType.DISCOUNT_ON_PURCHASE
    discount_type: EcommerceDiscountType = EcommerceDiscountType.PERCENT
    discount: Decimal = Field(gt=0)
    max_discount: Decimal | None = None
    min_purchase: Decimal = Decimal("0")
    shop_id: UUID | None = None
    customer_id: UUID | None = None
    start_date: str
    expire_date: str
    usage_limit: int | None = None
    total_limit: int | None = None
    is_active: bool = True


class CouponUpdateRequest(BaseModel):
    title: str | None = None
    coupon_type: EcommerceCouponType | None = None
    discount_type: EcommerceDiscountType | None = None
    discount: Decimal | None = Field(default=None, gt=0)
    max_discount: Decimal | None = None
    min_purchase: Decimal | None = None
    shop_id: UUID | None = None
    start_date: str | None = None
    expire_date: str | None = None
    usage_limit: int | None = None
    total_limit: int | None = None
    is_active: bool | None = None


class VendorCreateRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    phone: str | None = None
    shop_name: str = Field(min_length=2, max_length=255)
    shop_slug: str | None = None
    shop_tagline: str | None = None
    is_published: bool = False


class VendorUpdateRequest(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    phone: str | None = None
    is_active: bool | None = None
    shop_name: str | None = None
    shop_tagline: str | None = None
    is_published: bool | None = None


class ShopShippingMethodRequest(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=128)
    duration: str = "2-5 business days"
    cost: Decimal = Field(ge=0)
    currency: str = "UGX"
    is_active: bool = True
    sort_order: int = 0


class AdminWalletCreditRequest(BaseModel):
    customer_id: UUID
    amount: Decimal = Field(gt=0)
    reference: str = Field(default="admin_credit", max_length=128)
