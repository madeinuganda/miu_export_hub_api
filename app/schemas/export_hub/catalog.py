from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class CategoryCreate(BaseModel):
    label: str = Field(min_length=1, max_length=128)
    slug: str | None = Field(default=None, max_length=64)
    description: str | None = None
    parent_id: UUID | None = None
    sort_order: int = 0
    is_active: bool = True
    featured: bool = False
    image_url: str | None = Field(default=None, max_length=512)
    thumb_url: str | None = Field(default=None, max_length=512)


class CategoryUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=128)
    slug: str | None = Field(default=None, max_length=64)
    description: str | None = None
    parent_id: UUID | None = None
    sort_order: int | None = None
    is_active: bool | None = None
    featured: bool | None = None
    image_url: str | None = Field(default=None, max_length=512)
    thumb_url: str | None = Field(default=None, max_length=512)


class CategoryItem(BaseModel):
    id: UUID
    slug: str
    label: str
    description: str | None
    parent_id: UUID | None
    sort_order: int
    is_active: bool
    featured: bool
    image_url: str | None
    thumb_url: str | None
    product_count: int
    child_count: int
    created_at: datetime
    updated_at: datetime


class CategoryListResponse(BaseModel):
    items: list[CategoryItem]
    total: int
