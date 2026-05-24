from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, model_validator


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


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


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
    role_label: str = "Senior Trade Admin"


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
    account: BuyerAccountSummary
    onboarding_required: bool = False
    activation_required: bool = False
    must_change_password: bool = False


class SupplierAuthResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    account: SupplierAccountSummary
    onboarding_required: bool = False
    must_change_password: bool = False


class AdminAuthResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    account: AdminAccountSummary
    must_change_password: bool = False


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)
    new_password_confirm: str = Field(min_length=8, max_length=128)

    @model_validator(mode="after")
    def passwords_match(self) -> ChangePasswordRequest:
        if self.new_password != self.new_password_confirm:
            raise ValueError("new_password and new_password_confirm must match")
        return self


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


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ForgotPasswordResponse(BaseModel):
    ok: bool = True
    message: str


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=16, max_length=256)
    new_password: str = Field(min_length=8, max_length=128)
    new_password_confirm: str = Field(min_length=8, max_length=128)

    @model_validator(mode="after")
    def passwords_match(self) -> ResetPasswordRequest:
        if self.new_password != self.new_password_confirm:
            raise ValueError("new_password and new_password_confirm must match")
        return self


class ResetPasswordResponse(BaseModel):
    ok: bool = True
    message: str = "Password updated. You can sign in with your new password."
