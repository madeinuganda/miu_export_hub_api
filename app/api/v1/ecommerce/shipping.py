from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ecommerce.deps import CartOwnerContext, get_cart_owner
from app.core.shared.database import get_db
from app.schemas.ecommerce.order import ChooseShippingRequest
from app.services.ecommerce.shipping_service import EcommerceShippingService

router = APIRouter()


@router.get("/shipping-method/by-seller/{shop_id}/{seller_is}")
async def shipping_methods_by_seller(
    shop_id: UUID,
    seller_is: str = "seller",
    db: AsyncSession = Depends(get_db),
):
    _ = seller_is
    return await EcommerceShippingService.methods_for_shop(db, shop_id)


@router.get("/shipping-method/check-shipping-type")
async def check_shipping_type(shop_id: UUID = Query(...), seller_is: str = Query("seller")):
    _ = seller_is
    return {"shop_id": str(shop_id), "shipping_type": "order_wise"}


@router.post("/shipping-method/choose-for-order")
async def choose_for_order(
    data: ChooseShippingRequest,
    owner: CartOwnerContext = Depends(get_cart_owner),
    db: AsyncSession = Depends(get_db),
):
    result = await EcommerceShippingService.choose_for_order(
        db, owner, data.cart_group_id, data.id
    )
    await db.commit()
    return result


@router.get("/shipping-method/chosen")
async def chosen_shipping_methods(
    owner: CartOwnerContext = Depends(get_cart_owner),
    db: AsyncSession = Depends(get_db),
):
    return await EcommerceShippingService.chosen_methods(db, owner)
