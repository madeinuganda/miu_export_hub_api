from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, model_validator

from app.models.shared.enums import CustomerType
from app.schemas.shared.auth_common import LoginRequest


class CustomerRegisterRequest(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    phone: str | None = Field(default=None, max_length=50)
    password: str = Field(min_length=8, max_length=128)
    password_confirm: str = Field(min_length=8, max_length=128)
    customer_type: CustomerType = CustomerType.RETAIL
    guest_id: UUID | None = Field(
        default=None,
        description="Guest ID from GET /get-guest-id — cart items are merged into the new account",
    )

    @model_validator(mode="after")
    def passwords_match(self) -> CustomerRegisterRequest:
        if self.password != self.password_confirm:
            raise ValueError("password and password_confirm must match")
        return self


class CustomerLoginRequest(LoginRequest):
    guest_id: UUID | None = Field(
        default=None,
        description="Guest ID from GET /get-guest-id — cart items are merged on login",
    )


class CartMergeSummary(BaseModel):
    guest_id: UUID | None = None
    merged_items: int = 0
    merged_addresses: int = 0


class CustomerAccountSummary(BaseModel):
    id: UUID
    email: str
    first_name: str
    last_name: str
    customer_type: CustomerType
    must_change_password: bool
    email_verified: bool = False
    wallet_balance: float = 0.0


class EcommerceAdminAccountSummary(BaseModel):
    id: UUID
    email: str
    first_name: str
    last_name: str
    must_change_password: bool


class CustomerAuthResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    platform: str = "ecommerce"
    account: CustomerAccountSummary
    must_change_password: bool = False
    cart_merge: CartMergeSummary | None = None


class CustomerMeResponse(BaseModel):
    platform: str = "ecommerce"
    account: CustomerAccountSummary


class EcommerceAdminAuthResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    platform: str = "ecommerce"
    account: EcommerceAdminAccountSummary
    must_change_password: bool = False
    roles: list[str] = []
    permissions: list[str] = []


class EcommerceAdminMeResponse(BaseModel):
    account: EcommerceAdminAccountSummary
    platform: str = "ecommerce"
    roles: list[str] = []
    permissions: list[str] = []
    role_label: str = "E-Commerce Admin"


class PlatformInfo(BaseModel):
    id: str
    name: str
    description: str
    account_types: list[str]


class PlatformsResponse(BaseModel):
    platforms: list[PlatformInfo]


EcommerceLoginRequest = LoginRequest
