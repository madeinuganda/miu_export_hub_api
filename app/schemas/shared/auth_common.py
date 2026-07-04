from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, model_validator


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)
    new_password_confirm: str = Field(min_length=8, max_length=128)

    @model_validator(mode="after")
    def passwords_match(self) -> ChangePasswordRequest:
        if self.new_password != self.new_password_confirm:
            raise ValueError("new_password and new_password_confirm must match")
        return self


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
