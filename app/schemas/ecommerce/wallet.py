from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


class AddFundRequest(BaseModel):
    amount: float = Field(gt=0)
    payment_method: str = Field(default="pesapal")
    payment_platform: str = Field(default="app")
    payment_request_from: str = Field(default="app")


class AddFundResponse(BaseModel):
    redirect_link: str
    payment_id: UUID


class WalletConfigResponse(BaseModel):
    wallet_enabled: bool
    add_funds_enabled: bool
    minimum_add_fund_amount: float
    maximum_add_fund_amount: float
    currency: str = "UGX"
