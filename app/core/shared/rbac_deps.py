from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ecommerce.deps import require_ecommerce_admin_password_changed
from app.core.export_hub.deps import require_admin_password_changed
from app.core.shared.database import get_db
from app.core.shared.exceptions import AppError
from app.models.ecommerce.accounts import EcommerceAdminAccount
from app.models.export_hub.accounts import AdminAccount
from app.models.shared.enums import EcommerceAccountType, ExportHubAccountType, Platform
from app.services.shared.rbac_service import RbacService


def require_export_hub_permission(permission: str) -> Callable:
    async def _check(
        admin: AdminAccount = Depends(require_admin_password_changed),
        db: AsyncSession = Depends(get_db),
    ) -> AdminAccount:
        allowed = await RbacService.account_has_permission(
            db,
            platform=Platform.EXPORT_HUB,
            account_type=ExportHubAccountType.ADMIN.value,
            account_id=admin.id,
            permission=permission,
        )
        if not allowed:
            raise AppError(403, f"Missing permission: {permission}", "forbidden")
        return admin

    return _check


def require_ecommerce_permission(permission: str) -> Callable:
    async def _check(
        admin: EcommerceAdminAccount = Depends(require_ecommerce_admin_password_changed),
        db: AsyncSession = Depends(get_db),
    ) -> EcommerceAdminAccount:
        allowed = await RbacService.account_has_permission(
            db,
            platform=Platform.ECOMMERCE,
            account_type=EcommerceAccountType.ADMIN.value,
            account_id=admin.id,
            permission=permission,
        )
        if not allowed:
            raise AppError(403, f"Missing permission: {permission}", "forbidden")
        return admin

    return _check
