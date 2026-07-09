from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import Boolean, DateTime, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.shared.base import AuditMixin
from sqlalchemy import Enum as SAEnum

from app.models.shared.enums import DocumentStatus
from app.core.shared.database import Base


class BuyerSavedSupplier(AuditMixin, Base):
    __tablename__ = "buyer_saved_suppliers"
    __table_args__ = (UniqueConstraint("buyer_org_id", "supplier_org_id"),)

    buyer_org_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    supplier_org_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)


class FileRecord(AuditMixin, Base):
    __tablename__ = "files"

    storage_key: Mapped[str] = mapped_column(String(512), unique=True, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False)
    size_bytes: Mapped[int] = mapped_column(nullable=False)
    uploaded_by: Mapped[Optional[UUID]] = mapped_column(PGUUID(as_uuid=True), nullable=True)


class SupplierRegistrationDraft(AuditMixin, Base):
    __tablename__ = "supplier_registration_drafts"

    supplier_account_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), unique=True, nullable=False)
    step: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)


class BuyerRegistrationDraft(AuditMixin, Base):
    __tablename__ = "buyer_registration_drafts"

    buyer_account_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), unique=True, nullable=False)
    step: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)


class RegistrationDocument(AuditMixin, Base):
    __tablename__ = "registration_documents"

    org_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    document_type: Mapped[str] = mapped_column(String(64), nullable=False)
    file_id: Mapped[Optional[UUID]] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    status: Mapped[DocumentStatus] = mapped_column(
        SAEnum(DocumentStatus, name="document_status"), nullable=False
    )


class ExportChecklistTemplate(AuditMixin, Base):
    __tablename__ = "export_checklist_templates"

    section_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    item_key: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class ExportChecklistProgress(AuditMixin, Base):
    __tablename__ = "export_checklist_progress"
    __table_args__ = (UniqueConstraint("org_id", "item_key"),)

    org_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    item_key: Mapped[str] = mapped_column(String(64), nullable=False)
    completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class ExportChecklistDocument(AuditMixin, Base):
    """Uploaded supporting document for a single export checklist item."""

    __tablename__ = "export_checklist_documents"
    __table_args__ = (UniqueConstraint("org_id", "item_key"),)

    org_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    item_key: Mapped[str] = mapped_column(String(64), nullable=False)
    file_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    filename: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)


class AccountVerificationToken(AuditMixin, Base):
    """Email activation / verification tokens for buyer (and future supplier) accounts."""

    __tablename__ = "account_verification_tokens"

    buyer_account_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    purpose: Mapped[str] = mapped_column(String(32), default="email_activation", nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class PasswordResetToken(AuditMixin, Base):
    """One-time password reset tokens for buyer, supplier, and admin accounts."""

    __tablename__ = "password_reset_tokens"

    account_type: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    account_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class AdminActionLog(AuditMixin, Base):
    __tablename__ = "admin_actions_log"

    admin_account_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, nullable=True)
