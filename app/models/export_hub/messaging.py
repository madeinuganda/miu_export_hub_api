from __future__ import annotations

from uuid import UUID

from sqlalchemy import BigInteger, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.shared.base import AuditMixin
from app.core.shared.database import Base


class MessageAttachment(AuditMixin, Base):
    """A file attached to a message. `message_id` generically points at the
    id of the message row (currently always an `RfqMessage`, which is the
    single canonical thread for RFQ- and order-linked conversations)."""

    __tablename__ = "message_attachments"

    message_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    file_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
