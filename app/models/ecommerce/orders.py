from __future__ import annotations

import json
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy import Boolean, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.shared.database import Base
from app.models.shared.base import AuditMixin
from app.models.shared.db_types import str_enum
from app.models.shared.enums import (
    EcommerceDiscountType,
    EcommerceOrderStatus,
    EcommercePaymentMethod,
    EcommercePaymentStatus,
)


class EcommerceCartShipping(AuditMixin, Base):
    """Selected shipping method per shop cart group (Laravel cart_shipping parity)."""

    __tablename__ = "ecommerce_cart_shipping"

    owner_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    is_guest: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    cart_group_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    shipping_method_code: Mapped[str] = mapped_column(String(64), nullable=False)
    shipping_method_title: Mapped[str] = mapped_column(String(128), nullable=False)
    shipping_cost: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)


class EcommerceOrder(AuditMixin, Base):
    __tablename__ = "ecommerce_orders"

    public_id: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    order_group_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    customer_id: Mapped[Optional[UUID]] = mapped_column(PGUUID(as_uuid=True), nullable=True, index=True)
    guest_id: Mapped[Optional[UUID]] = mapped_column(PGUUID(as_uuid=True), nullable=True, index=True)
    is_guest: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    shop_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    order_status: Mapped[EcommerceOrderStatus] = mapped_column(
        str_enum(EcommerceOrderStatus, name="ecommerce_order_status"),
        default=EcommerceOrderStatus.PENDING,
        nullable=False,
    )
    payment_status: Mapped[EcommercePaymentStatus] = mapped_column(
        str_enum(EcommercePaymentStatus, name="ecommerce_payment_status"),
        default=EcommercePaymentStatus.UNPAID,
        nullable=False,
    )
    payment_method: Mapped[EcommercePaymentMethod] = mapped_column(
        str_enum(EcommercePaymentMethod, name="ecommerce_payment_method"),
        nullable=False,
    )
    transaction_ref: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    order_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    shipping_cost: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"), nullable=False)
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"), nullable=False)
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"), nullable=False)
    paid_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="UGX", nullable=False)
    shipping_address_id: Mapped[Optional[UUID]] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    shipping_address_snapshot: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    order_note: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)


class EcommerceOrderItem(AuditMixin, Base):
    __tablename__ = "ecommerce_order_items"

    order_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    product_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    shop_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    discount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"), nullable=False)
    discount_type: Mapped[EcommerceDiscountType] = mapped_column(
        str_enum(EcommerceDiscountType, name="ecommerce_order_item_discount_type"),
        default=EcommerceDiscountType.PERCENT,
        nullable=False,
    )
    product_name: Mapped[str] = mapped_column(String(512), nullable=False)
    product_slug: Mapped[str] = mapped_column(String(256), nullable=False)
    product_thumbnail: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)


class EcommercePaymentRequest(AuditMixin, Base):
    """Pending Pesapal payment — order is created on successful callback."""

    __tablename__ = "ecommerce_payment_requests"

    owner_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    is_guest: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    payment_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency_code: Mapped[str] = mapped_column(String(8), default="UGX", nullable=False)
    is_paid: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    payment_method: Mapped[str] = mapped_column(String(32), default="pesapal", nullable=False)
    transaction_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    payer_information: Mapped[str] = mapped_column(Text, nullable=False)
    additional_data: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    order_ids_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    def payer(self) -> dict:
        return json.loads(self.payer_information)

    def additional(self) -> dict:
        if not self.additional_data:
            return {}
        return json.loads(self.additional_data)

    def order_ids(self) -> list[str]:
        if not self.order_ids_json:
            return []
        return json.loads(self.order_ids_json)
