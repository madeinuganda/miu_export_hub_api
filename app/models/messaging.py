from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, Enum, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import AuditMixin
from app.models.enums import ConversationType, SenderRole
from app.core.database import Base


class ConversationThread(AuditMixin, Base):
    __tablename__ = "conversation_threads"

    thread_type: Mapped[ConversationType] = mapped_column(Enum(ConversationType, name="conversation_type"), nullable=False)
    buyer_org_id: Mapped[Optional[UUID]] = mapped_column(PGUUID(as_uuid=True), nullable=True, index=True)
    supplier_org_id: Mapped[Optional[UUID]] = mapped_column(PGUUID(as_uuid=True), nullable=True, index=True)
    subject: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)


class ConversationMessage(AuditMixin, Base):
    __tablename__ = "conversation_messages"

    thread_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    sender_role: Mapped[SenderRole] = mapped_column(Enum(SenderRole, name="message_sender_role"), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    order_id: Mapped[Optional[UUID]] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    rfq_id: Mapped[Optional[UUID]] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class MessageAttachment(AuditMixin, Base):
    __tablename__ = "message_attachments"

    message_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    file_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
