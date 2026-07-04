from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy import Boolean, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.shared.database import Base
from app.models.shared.base import AuditMixin


class EcommerceShippingAddress(AuditMixin, Base):
    """Shipping/billing address for guests (EcommerceGuest.id) or customers (CustomerAccount.id)."""

    __tablename__ = "ecommerce_shipping_addresses"

    owner_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    is_guest: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    contact_person_name: Mapped[str] = mapped_column(String(128), nullable=False)
    address_type: Mapped[str] = mapped_column(String(32), default="home", nullable=False)
    address: Mapped[str] = mapped_column(String(512), nullable=False)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    zip: Mapped[str] = mapped_column(String(32), nullable=False)
    country: Mapped[str] = mapped_column(String(100), nullable=False)
    phone: Mapped[str] = mapped_column(String(50), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    latitude: Mapped[str] = mapped_column(String(32), default="0", nullable=False)
    longitude: Mapped[str] = mapped_column(String(32), default="0", nullable=False)
    is_billing: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
