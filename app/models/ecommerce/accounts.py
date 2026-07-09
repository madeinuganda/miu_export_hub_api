from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.shared.database import Base
from app.models.shared.base import AuditMixin
from app.models.shared.db_types import str_enum
from app.models.shared.enums import CustomerType


class _EcommerceAccountMixin:
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    email_verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    two_factor_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class CustomerAccount(_EcommerceAccountMixin, AuditMixin, Base):
    """Retail / shop storefront customer — separate from Export Hub buyers."""

    __tablename__ = "customer_accounts"

    customer_type: Mapped[CustomerType] = mapped_column(
        str_enum(CustomerType, name="customer_type"),
        default=CustomerType.RETAIL,
        nullable=False,
    )
    referral_code: Mapped[Optional[str]] = mapped_column(String(32), unique=True, nullable=True)
    is_guest: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    wallet_balance: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"), nullable=False)


class CustomerSession(AuditMixin, Base):
    __tablename__ = "customer_sessions"

    customer_account_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    refresh_token_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    user_agent: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class SellerAccount(_EcommerceAccountMixin, AuditMixin, Base):
    """Marketplace vendor/seller — separate from Export Hub suppliers."""

    __tablename__ = "seller_accounts"


class SellerSession(AuditMixin, Base):
    __tablename__ = "seller_sessions"

    seller_account_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    refresh_token_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    user_agent: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class EcommerceShop(AuditMixin, Base):
    __tablename__ = "ecommerce_shops"

    seller_account_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    tagline: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class EcommerceAdminAccount(_EcommerceAccountMixin, AuditMixin, Base):
    """Back-office admin for the retail e-commerce platform."""

    __tablename__ = "ecommerce_admin_accounts"

    invited_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    invited_by: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("ecommerce_admin_accounts.id"), nullable=True
    )


class EcommerceAdminSession(AuditMixin, Base):
    __tablename__ = "ecommerce_admin_sessions"

    ecommerce_admin_account_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    refresh_token_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    user_agent: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class CustomerAddress(AuditMixin, Base):
    __tablename__ = "customer_addresses"

    customer_account_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    line1: Mapped[str] = mapped_column(String(255), nullable=False)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    country: Mapped[str] = mapped_column(String(100), nullable=False)
    postal_code: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
