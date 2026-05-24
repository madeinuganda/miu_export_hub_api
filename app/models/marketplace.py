from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import AuditMixin
from app.core.database import Base


class CmsSiteSettings(AuditMixin, Base):
    __tablename__ = "cms_site_settings"

    announcement_text: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    footer_links: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)


class CmsHero(AuditMixin, Base):
    __tablename__ = "cms_hero"

    eyebrow: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    subtitle: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cta_primary_label: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    cta_primary_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    cta_secondary_label: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    cta_secondary_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    background_image_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class CmsTrustItem(AuditMixin, Base):
    __tablename__ = "cms_trust_items"

    icon: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class CmsCategory(AuditMixin, Base):
    __tablename__ = "cms_categories"

    category_id: Mapped[Optional[UUID]] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    image_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    copy_text: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class CmsFeaturedProduct(AuditMixin, Base):
    __tablename__ = "cms_featured_products"

    product_id: Mapped[Optional[UUID]] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    snapshot: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class CmsHowItWorksStep(AuditMixin, Base):
    __tablename__ = "cms_how_it_works_steps"

    step_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    icon: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class CmsFeature(AuditMixin, Base):
    __tablename__ = "cms_features"

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    icon: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class CmsTestimonial(AuditMixin, Base):
    __tablename__ = "cms_testimonials"

    quote: Mapped[str] = mapped_column(Text, nullable=False)
    author: Mapped[str] = mapped_column(String(128), nullable=False)
    role: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    company: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    country: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    avatar_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class CmsTradeCta(AuditMixin, Base):
    __tablename__ = "cms_trade_cta"

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    button_label: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    button_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class CmsSupplierHero(AuditMixin, Base):
    __tablename__ = "cms_supplier_hero"

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cta_label: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    cta_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class CmsNavLink(AuditMixin, Base):
    __tablename__ = "cms_nav_links"

    label: Mapped[str] = mapped_column(String(128), nullable=False)
    href: Mapped[str] = mapped_column(String(512), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
