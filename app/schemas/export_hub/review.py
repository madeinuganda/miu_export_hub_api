from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


class ReviewCreateRequest(BaseModel):
    product_id: UUID
    order_id: UUID | None = None
    rating: int = Field(ge=1, le=5)
    title: str | None = Field(default=None, max_length=128)
    comment: str | None = None
