from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


class ChooseShippingRequest(BaseModel):
    cart_group_id: UUID
    id: str = Field(description="Shipping method code, e.g. flat_standard")


class PlaceOrderRequest(BaseModel):
    address_id: UUID | None = None
    order_note: str | None = Field(default=None, max_length=512)


class DigitalPaymentRequest(BaseModel):
    payment_method: str = Field(default="pesapal")
    payment_platform: str = Field(default="app")
    payment_request_from: str = Field(default="app")
    address_id: UUID | None = None
    order_note: str | None = Field(default=None, max_length=512)
    payer_email: str | None = None
    payer_name: str | None = None
    payer_phone: str | None = None
    coupon_code: str | None = None


class PlaceOrderResponse(BaseModel):
    order_ids: list[UUID]
    order_numbers: list[str]
    new_user: bool = False


class DigitalPaymentResponse(BaseModel):
    redirect_link: str
    payment_id: UUID
