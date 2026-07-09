from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


RoleType = Literal["supplier", "buyer"]


class TestimonialCreate(BaseModel):
    quote: str = Field(min_length=1)
    author: str = Field(min_length=1, max_length=128)
    company: str | None = Field(default=None, max_length=255)
    detail: str | None = Field(default=None, max_length=255)
    role_type: RoleType = "supplier"
    metric: str | None = Field(default=None, max_length=128)
    rating: int = Field(default=5, ge=1, le=5)
    sort_order: int = 0
    is_active: bool = True
    avatar_url: str | None = Field(default=None, max_length=512)


class TestimonialUpdate(BaseModel):
    quote: str | None = Field(default=None, min_length=1)
    author: str | None = Field(default=None, min_length=1, max_length=128)
    company: str | None = Field(default=None, max_length=255)
    detail: str | None = Field(default=None, max_length=255)
    role_type: RoleType | None = None
    metric: str | None = Field(default=None, max_length=128)
    rating: int | None = Field(default=None, ge=1, le=5)
    sort_order: int | None = None
    is_active: bool | None = None
    avatar_url: str | None = Field(default=None, max_length=512)


class TestimonialItem(BaseModel):
    id: UUID
    quote: str
    author: str
    company: str | None
    detail: str | None
    role_type: RoleType
    metric: str | None
    rating: int
    avatar_url: str | None
    sort_order: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


class TestimonialListResponse(BaseModel):
    items: list[TestimonialItem]
    total: int


class PublicTestimonialItem(BaseModel):
    id: UUID
    quote: str
    name: str
    company: str | None
    detail: str | None
    roleType: RoleType
    metric: str | None
    rating: int
    avatarUrl: str | None
    initial: str


class PublicTestimonialListResponse(BaseModel):
    items: list[PublicTestimonialItem]
