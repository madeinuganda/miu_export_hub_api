from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.shared.database import get_db
from app.core.shared.rbac_deps import require_ecommerce_permission
from app.models.ecommerce.accounts import EcommerceAdminAccount
from app.services.ecommerce.admin_order_service import (
    AdminOrderDashboardResponse,
    AdminOrderStatusUpdateRequest,
    EcommerceAdminOrderService,
)

router = APIRouter(prefix="/admin")


@router.get("/orders/dashboard", response_model=AdminOrderDashboardResponse)
async def orders_dashboard(
    _: EcommerceAdminAccount = Depends(require_ecommerce_permission("ecommerce.orders.manage")),
    db: AsyncSession = Depends(get_db),
):
    return await EcommerceAdminOrderService.dashboard(db)


@router.get("/orders")
async def list_orders(
    status: str = Query("all"),
    shop_id: UUID | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(1, ge=1),
    _: EcommerceAdminAccount = Depends(require_ecommerce_permission("ecommerce.orders.manage")),
    db: AsyncSession = Depends(get_db),
):
    return await EcommerceAdminOrderService.list_orders(
        db, status=status, shop_id=shop_id, limit=limit, offset=offset
    )


@router.get("/orders/{order_id}")
async def order_detail(
    order_id: UUID,
    _: EcommerceAdminAccount = Depends(require_ecommerce_permission("ecommerce.orders.manage")),
    db: AsyncSession = Depends(get_db),
):
    return await EcommerceAdminOrderService.order_detail(db, order_id)


@router.put("/orders/{order_id}/status")
async def update_order_status(
    order_id: UUID,
    data: AdminOrderStatusUpdateRequest,
    _: EcommerceAdminAccount = Depends(require_ecommerce_permission("ecommerce.orders.manage")),
    db: AsyncSession = Depends(get_db),
):
    result = await EcommerceAdminOrderService.update_status(db, order_id, data.order_status)
    await db.commit()
    return result
