from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel


class SellerAccountSummary(BaseModel):
    id: UUID
    email: str
    first_name: str
    last_name: str
    must_change_password: bool
    email_verified: bool = False


class SellerShopSummary(BaseModel):
    id: UUID
    name: str
    slug: str
    is_published: bool


class SellerAuthResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    platform: str = "ecommerce"
    account: SellerAccountSummary
    shop: SellerShopSummary | None = None
    must_change_password: bool = False


class SellerMeResponse(BaseModel):
    platform: str = "ecommerce"
    account: SellerAccountSummary
    shop: SellerShopSummary | None = None


class SellerOrderStatusUpdateRequest(BaseModel):
    order_id: UUID
    order_status: str
