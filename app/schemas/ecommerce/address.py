from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class ShippingAddressCreateRequest(BaseModel):
    contact_person_name: str = Field(min_length=1, max_length=128)
    address_type: str = Field(min_length=1, max_length=32)
    address: str = Field(min_length=1, max_length=512)
    city: str = Field(min_length=1, max_length=100)
    zip: str = Field(min_length=1, max_length=32)
    country: str = Field(min_length=1, max_length=100)
    phone: str = Field(min_length=1, max_length=50)
    email: EmailStr | None = None
    latitude: str = Field(default="0", max_length=32)
    longitude: str = Field(default="0", max_length=32)
    is_billing: bool = False


class ShippingAddressUpdateRequest(ShippingAddressCreateRequest):
    id: UUID


class ShippingAddressDeleteRequest(BaseModel):
    address_id: UUID


class ShippingAddressResponse(BaseModel):
    id: UUID
    contact_person_name: str
    address_type: str
    address: str
    city: str
    zip: str
    country: str
    phone: str
    email: str | None
    latitude: str
    longitude: str
    is_billing: bool
    is_default: bool
    is_guest: bool
