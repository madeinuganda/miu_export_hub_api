from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class PaginatedProductsResponse(BaseModel):
    total_size: int
    limit: int
    offset: int
    min_price: Decimal | None = None
    max_price: Decimal | None = None
    products: list[dict]


class CategoryTreeItem(BaseModel):
    id: UUID
    name: str
    slug: str
    icon: str | None = None
    parent_id: UUID | None = None
    position: str
    home_status: bool
    priority: int
    product_count: int = 0
    childes: list["CategoryTreeItem"] = []


class BrandItem(BaseModel):
    id: UUID
    name: str
    slug: str
    image: str | None = None
    brand_products_count: int = 0


class BrandListResponse(BaseModel):
    total_size: int
    limit: int
    offset: int
    brands: list[BrandItem]


class GuestIdResponse(BaseModel):
    guest_id: UUID


class ProductFilterQuery(BaseModel):
    search: str | None = None
    category: list[UUID] | None = None
    brand: list[UUID] | None = None
    sort_by: str | None = Field(default=None, pattern="^(low-high|high-low|a-z|z-a|latest)$")
    price_min: Decimal | None = None
    price_max: Decimal | None = None
    limit: int = Field(default=10, ge=1, le=100)
    offset: int = Field(default=1, ge=1)


class ProductSearchQuery(BaseModel):
    name: str = Field(min_length=1, max_length=256)
    limit: int = Field(default=10, ge=1, le=100)
    offset: int = Field(default=1, ge=1)
