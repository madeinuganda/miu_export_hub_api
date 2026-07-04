from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ecommerce.deps import get_current_seller, require_seller_password_changed
from app.core.shared.database import get_db
from app.models.ecommerce.accounts import SellerAccount
from app.schemas.ecommerce.seller import SellerOrderStatusUpdateRequest
from app.services.ecommerce.seller_order_service import EcommerceSellerOrderService

router = APIRouter(prefix="/seller", tags=["E-Commerce · Seller"])


@router.get("/orders/list")
async def seller_order_list(
    status: str = Query("all"),
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(1, ge=1),
    seller: SellerAccount = Depends(require_seller_password_changed),
    db: AsyncSession = Depends(get_db),
):
    return await EcommerceSellerOrderService.list_orders(
        db, seller, status=status, limit=limit, offset=offset
    )


@router.get("/orders/details/{order_id}")
async def seller_order_details(
    order_id: UUID,
    seller: SellerAccount = Depends(require_seller_password_changed),
    db: AsyncSession = Depends(get_db),
):
    return await EcommerceSellerOrderService.order_details(db, seller, order_id)


@router.put("/orders/status")
async def seller_update_order_status(
    data: SellerOrderStatusUpdateRequest,
    seller: SellerAccount = Depends(require_seller_password_changed),
    db: AsyncSession = Depends(get_db),
):
    result = await EcommerceSellerOrderService.update_order_status(
        db, seller, data.order_id, data.order_status
    )
    await db.commit()
    return result
