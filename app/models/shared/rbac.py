from __future__ import annotations

from uuid import UUID

from sqlalchemy import String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.shared.database import Base
from app.models.shared.base import AuditMixin
from app.models.shared.db_types import str_enum
from app.models.shared.enums import EcommerceAccountType, ExportHubAccountType, Platform


class Permission(AuditMixin, Base):
    __tablename__ = "permissions"
    __table_args__ = (UniqueConstraint("platform", "code"),)

    platform: Mapped[Platform] = mapped_column(str_enum(Platform, name="platform"), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)


class Role(AuditMixin, Base):
    __tablename__ = "roles"
    __table_args__ = (UniqueConstraint("platform", "code"),)

    platform: Mapped[Platform] = mapped_column(str_enum(Platform, name="platform"), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_system: Mapped[bool] = mapped_column(default=True, nullable=False)


class RolePermission(AuditMixin, Base):
    __tablename__ = "role_permissions"
    __table_args__ = (UniqueConstraint("role_id", "permission_id"),)

    role_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    permission_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)


class AccountRoleAssignment(AuditMixin, Base):
    """Links any platform account to RBAC roles."""

    __tablename__ = "account_role_assignments"
    __table_args__ = (UniqueConstraint("platform", "account_type", "account_id", "role_id"),)

    platform: Mapped[Platform] = mapped_column(str_enum(Platform, name="platform"), nullable=False, index=True)
    account_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    account_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    role_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)


def export_hub_admin_assignment(account_id: UUID, role_id: UUID) -> AccountRoleAssignment:
    return AccountRoleAssignment(
        platform=Platform.EXPORT_HUB,
        account_type=ExportHubAccountType.ADMIN.value,
        account_id=account_id,
        role_id=role_id,
    )


def ecommerce_admin_assignment(account_id: UUID, role_id: UUID) -> AccountRoleAssignment:
    return AccountRoleAssignment(
        platform=Platform.ECOMMERCE,
        account_type=EcommerceAccountType.ADMIN.value,
        account_id=account_id,
        role_id=role_id,
    )
