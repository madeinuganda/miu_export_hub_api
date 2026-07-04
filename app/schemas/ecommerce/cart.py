from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class AddToCartRequest(BaseModel):
    id: UUID = Field(description="Product ID")
    quantity: int = Field(default=1, ge=1, le=999)


class UpdateCartRequest(BaseModel):
    key: UUID = Field(description="Cart item ID")
    quantity: int = Field(ge=1, le=999)


class RemoveCartRequest(BaseModel):
    key: UUID = Field(description="Cart item ID")


class SelectCartItemsRequest(BaseModel):
    ids: list[UUID] = Field(min_length=1)
    action: str = Field(pattern="^(checked|unchecked)$")


class CartSummaryResponse(BaseModel):
    item_count: int
    checked_item_count: int
    subtotal: Decimal
    discount_total: Decimal
    shipping_cost: Decimal
    tax: Decimal
    total: Decimal
    currency: str = "UGX"
