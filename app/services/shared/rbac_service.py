from __future__ import annotations

from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.core.shared.permissions import PLATFORM_PERMISSIONS, PLATFORM_ROLE_PERMISSIONS
from app.models.shared.enums import EcommerceAccountType, ExportHubAccountType, Platform
from app.models.shared.rbac import AccountRoleAssignment, Permission, Role, RolePermission


def _humanize_role(code: str) -> str:
    return code.split(".", 1)[-1].replace("_", " ").title()


async def seed_default_rbac(db: AsyncSession) -> None:
    await db.run_sync(_seed_default_rbac_sync)


def seed_default_rbac_sync(bind: Session | sa.Connection) -> None:
    _seed_default_rbac_sync(bind)


def _seed_default_rbac_sync(bind: Session | sa.Connection) -> None:
    session = bind if isinstance(bind, Session) else Session(bind=bind)
    own_session = not isinstance(bind, Session)
    try:
        existing = session.execute(select(Permission.id).limit(1)).first()
        if existing:
            return

        perm_ids: dict[str, UUID] = {}
        for platform, catalog in PLATFORM_PERMISSIONS.items():
            for code, description in catalog.items():
                perm = Permission(platform=platform, code=code, description=description)
                session.add(perm)
                session.flush()
                perm_ids[code] = perm.id

        role_ids: dict[str, UUID] = {}
        for platform, roles in PLATFORM_ROLE_PERMISSIONS.items():
            for role_code, permission_codes in roles.items():
                role = Role(
                    platform=platform,
                    code=role_code,
                    name=_humanize_role(role_code),
                    description=f"System role for {platform.value}",
                    is_system=True,
                )
                session.add(role)
                session.flush()
                role_ids[role_code] = role.id
                for perm_code in permission_codes:
                    session.add(
                        RolePermission(role_id=role.id, permission_id=perm_ids[perm_code])
                    )

        _assign_export_hub_super_admin(session, role_ids.get("export_hub.super_admin"))
        _assign_ecommerce_super_admin(session, role_ids.get("ecommerce.super_admin"))
        session.commit()
    finally:
        if own_session:
            session.close()


def _assign_export_hub_super_admin(session: Session, role_id: UUID | None) -> None:
    if not role_id:
        return
    from app.models.export_hub.accounts import AdminAccount

    admins = session.execute(
        select(AdminAccount).where(AdminAccount.deleted_at.is_(None))
    ).scalars()
    for admin in admins:
        exists = session.execute(
            select(AccountRoleAssignment.id).where(
                AccountRoleAssignment.platform == Platform.EXPORT_HUB,
                AccountRoleAssignment.account_type == ExportHubAccountType.ADMIN.value,
                AccountRoleAssignment.account_id == admin.id,
                AccountRoleAssignment.role_id == role_id,
                AccountRoleAssignment.deleted_at.is_(None),
            )
        ).first()
        if exists:
            continue
        session.add(
            AccountRoleAssignment(
                platform=Platform.EXPORT_HUB,
                account_type=ExportHubAccountType.ADMIN.value,
                account_id=admin.id,
                role_id=role_id,
                created_by=admin.id,
                updated_by=admin.id,
            )
        )


def _assign_ecommerce_super_admin(session: Session, role_id: UUID | None) -> None:
    if not role_id:
        return
    from app.models.ecommerce.accounts import EcommerceAdminAccount

    admins = session.execute(
        select(EcommerceAdminAccount).where(EcommerceAdminAccount.deleted_at.is_(None))
    ).scalars()
    for admin in admins:
        exists = session.execute(
            select(AccountRoleAssignment.id).where(
                AccountRoleAssignment.platform == Platform.ECOMMERCE,
                AccountRoleAssignment.account_type == EcommerceAccountType.ADMIN.value,
                AccountRoleAssignment.account_id == admin.id,
                AccountRoleAssignment.role_id == role_id,
                AccountRoleAssignment.deleted_at.is_(None),
            )
        ).first()
        if exists:
            continue
        session.add(
            AccountRoleAssignment(
                platform=Platform.ECOMMERCE,
                account_type=EcommerceAccountType.ADMIN.value,
                account_id=admin.id,
                role_id=role_id,
                created_by=admin.id,
                updated_by=admin.id,
            )
        )


class RbacService:
    @staticmethod
    async def get_permissions(
        db: AsyncSession,
        *,
        platform: Platform,
        account_type: str,
        account_id: UUID,
    ) -> set[str]:
        result = await db.execute(
            select(Permission.code)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .join(Role, Role.id == RolePermission.role_id)
            .join(
                AccountRoleAssignment,
                AccountRoleAssignment.role_id == Role.id,
            )
            .where(
                AccountRoleAssignment.platform == platform,
                AccountRoleAssignment.account_type == account_type,
                AccountRoleAssignment.account_id == account_id,
                AccountRoleAssignment.deleted_at.is_(None),
                Role.deleted_at.is_(None),
                Permission.deleted_at.is_(None),
            )
        )
        return set(result.scalars().all())

    @staticmethod
    async def get_roles(
        db: AsyncSession,
        *,
        platform: Platform,
        account_type: str,
        account_id: UUID,
    ) -> list[str]:
        result = await db.execute(
            select(Role.code)
            .join(AccountRoleAssignment, AccountRoleAssignment.role_id == Role.id)
            .where(
                AccountRoleAssignment.platform == platform,
                AccountRoleAssignment.account_type == account_type,
                AccountRoleAssignment.account_id == account_id,
                AccountRoleAssignment.deleted_at.is_(None),
                Role.deleted_at.is_(None),
            )
        )
        return list(result.scalars().all())

    @staticmethod
    async def account_has_permission(
        db: AsyncSession,
        *,
        platform: Platform,
        account_type: str,
        account_id: UUID,
        permission: str,
    ) -> bool:
        perms = await RbacService.get_permissions(
            db, platform=platform, account_type=account_type, account_id=account_id
        )
        return permission in perms
