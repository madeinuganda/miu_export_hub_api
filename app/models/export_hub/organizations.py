from __future__ import annotations

from datetime import date, datetime  # noqa: F401 — datetime used by onboarding_submitted_at
from typing import Optional
from uuid import UUID

from sqlalchemy import Boolean, Date, DateTime, Enum, SmallInteger, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.shared.base import AuditMixin
from app.models.shared.db_types import str_enum
from app.models.shared.enums import CertificationStatus, OrgMemberRole, VerificationStatus
from app.core.shared.database import Base


class BuyerOrganization(AuditMixin, Base):
    __tablename__ = "buyer_organizations"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    country: Mapped[str] = mapped_column(String(100), nullable=False)
    city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    industry: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    website: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    procurement_contact: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    job_title: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    onboarding_status: Mapped[VerificationStatus] = mapped_column(
        str_enum(VerificationStatus, name="buyer_onboarding_status"),
        default=VerificationStatus.DRAFT,
        nullable=False,
    )
    onboarding_submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    verified_buyer: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    logo_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)


class BuyerOrganizationMember(AuditMixin, Base):
    __tablename__ = "buyer_organization_members"
    __table_args__ = (UniqueConstraint("org_id", "buyer_account_id"),)

    org_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    buyer_account_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    role: Mapped[OrgMemberRole] = mapped_column(Enum(OrgMemberRole, name="org_member_role"), nullable=False)


class SupplierOrganization(AuditMixin, Base):
    __tablename__ = "supplier_organizations"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    business_type: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    subcategory: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    region: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    district: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    tagline: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    website: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    short_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    brand_story: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    verification_status: Mapped[VerificationStatus] = mapped_column(
        str_enum(VerificationStatus, name="verification_status"),
        default=VerificationStatus.DRAFT,
        nullable=False,
    )
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    storefront_published: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    featured: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    banner_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    banner_style: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    logo_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    established_year: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    team_size: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    export_markets: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)


class SupplierOrganizationMember(AuditMixin, Base):
    __tablename__ = "supplier_organization_members"
    __table_args__ = (UniqueConstraint("org_id", "supplier_account_id"),)

    org_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    supplier_account_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    role: Mapped[OrgMemberRole] = mapped_column(Enum(OrgMemberRole, name="supplier_org_member_role"), nullable=False)


class SupplierVerificationStep(AuditMixin, Base):
    __tablename__ = "supplier_verification_steps"
    __table_args__ = (UniqueConstraint("org_id", "step_key"),)

    org_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    step_key: Mapped[str] = mapped_column(String(64), nullable=False)
    done: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class SupplierCertification(AuditMixin, Base):
    __tablename__ = "supplier_certifications"

    org_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[CertificationStatus] = mapped_column(
        Enum(CertificationStatus, name="certification_status"), nullable=False
    )
    expiry_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    document_id: Mapped[Optional[UUID]] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    sort_order: Mapped[int] = mapped_column(default=0, nullable=False)


class SupplierGalleryPhoto(AuditMixin, Base):
    __tablename__ = "supplier_gallery_photos"

    org_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    image_url: Mapped[str] = mapped_column(String(512), nullable=False)
    caption: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    sort_order: Mapped[int] = mapped_column(default=0, nullable=False)
