from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, model_validator

from app.schemas.shared.auth_common import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    LoginRequest,
    ResetPasswordRequest,
    ResetPasswordResponse,
)

__all__ = [
    "SignUpBase",
    "BuyerRegisterRequest",
    "SupplierRegisterRequest",
    "LoginRequest",
    "BuyerAccountSummary",
    "SupplierAccountSummary",
    "AdminAccountSummary",
    "AdminMeResponse",
    "BuyerRegisterResponse",
    "BuyerActivateRequest",
    "BuyerResendActivationRequest",
    "BuyerAuthResponse",
    "SupplierAuthResponse",
    "AdminAuthResponse",
    "ChangePasswordRequest",
    "AdminInviteRequest",
    "AdminInviteResponse",
    "ForgotPasswordRequest",
    "ForgotPasswordResponse",
    "ResetPasswordRequest",
    "ResetPasswordResponse",
]


class SignUpBase(BaseModel):
    company: str = Field(min_length=2, max_length=255)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    phone: str | None = Field(default=None, max_length=50)
    password: str = Field(min_length=8, max_length=128)
    password_confirm: str = Field(min_length=8, max_length=128)

    @model_validator(mode="after")
    def passwords_match(self) -> SignUpBase:
        if self.password != self.password_confirm:
            raise ValueError("password and password_confirm must match")
        return self


class BuyerRegisterRequest(SignUpBase):
    """Buyer self-service sign-up with password."""


class SupplierRegisterRequest(SignUpBase):
    """Supplier self-service sign-up with password."""


class BuyerAccountSummary(BaseModel):
    id: UUID
    email: str
    first_name: str
    last_name: str
    must_change_password: bool
    email_verified: bool = False


class SupplierAccountSummary(BaseModel):
    id: UUID
    email: str
    first_name: str
    last_name: str
    must_change_password: bool


class AdminAccountSummary(BaseModel):
    id: UUID
    email: str
    first_name: str
    last_name: str
    must_change_password: bool


class AdminMeResponse(BaseModel):
    account: AdminAccountSummary
    platform: str = "export_hub"
    roles: list[str] = []
    permissions: list[str] = []
    role_label: str = "Export Hub Admin"


class BuyerRegisterResponse(BaseModel):
    message: str
    email: str
    activation_required: bool = True


class BuyerActivateRequest(BaseModel):
    token: str = Field(min_length=16, max_length=256)


class BuyerResendActivationRequest(BaseModel):
    email: EmailStr


class BuyerAuthResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    platform: str = "export_hub"
    account: BuyerAccountSummary
    onboarding_required: bool = False
    activation_required: bool = False
    must_change_password: bool = False


class SupplierAuthResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    platform: str = "export_hub"
    account: SupplierAccountSummary
    onboarding_required: bool = False
    must_change_password: bool = False


class AdminAuthResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    platform: str = "export_hub"
    account: AdminAccountSummary
    must_change_password: bool = False
    roles: list[str] = []
    permissions: list[str] = []


class AdminInviteRequest(BaseModel):
    email: EmailStr
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    phone: str | None = Field(default=None, max_length=50)


class AdminInviteResponse(BaseModel):
    account_id: UUID
    email: str
    temporary_password: str
    message: str = "Share the temporary password securely. Admin must change it on first login."
