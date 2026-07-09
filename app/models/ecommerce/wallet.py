from __future__ import annotations

from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy import Numeric, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.shared.database import Base
from app.models.shared.base import AuditMixin
from app.models.shared.db_types import str_enum
from app.models.shared.enums import EcommerceWalletTransactionType


class EcommerceWalletTransaction(AuditMixin, Base):
    __tablename__ = "ecommerce_wallet_transactions"

    customer_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    transaction_ref: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    credit: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"), nullable=False)
    debit: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"), nullable=False)
    balance_after: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    transaction_type: Mapped[EcommerceWalletTransactionType] = mapped_column(
        str_enum(EcommerceWalletTransactionType, name="ecommerce_wallet_transaction_type"),
        nullable=False,
    )
    reference: Mapped[str] = mapped_column(String(128), nullable=False)
    payment_method: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
