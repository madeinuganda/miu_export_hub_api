from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ecommerce.deps import CartOwnerContext, get_cart_owner
from app.core.shared.database import get_db
from app.schemas.ecommerce.cart import (
    AddToCartRequest,
    CartSummaryResponse,
    RemoveCartRequest,
    SelectCartItemsRequest,
    UpdateCartRequest,
)
from app.services.ecommerce.cart_service import EcommerceCartService

router = APIRouter(prefix="/cart", tags=["E-Commerce · Cart"])


@router.get("/")
async def get_cart(
    owner: CartOwnerContext = Depends(get_cart_owner),
    db: AsyncSession = Depends(get_db),
):
    return await EcommerceCartService.list_cart(db, owner)


@router.get("/summary", response_model=CartSummaryResponse)
async def cart_summary(
    owner: CartOwnerContext = Depends(get_cart_owner),
    db: AsyncSession = Depends(get_db),
):
    data = await EcommerceCartService.summary(db, owner)
    await db.commit()
    return CartSummaryResponse(**data)


@router.post("/add")
async def add_to_cart(
    data: AddToCartRequest,
    owner: CartOwnerContext = Depends(get_cart_owner),
    db: AsyncSession = Depends(get_db),
):
    result = await EcommerceCartService.add_to_cart(db, owner, data.id, data.quantity)
    await db.commit()
    return result


@router.put("/update")
async def update_cart(
    data: UpdateCartRequest,
    owner: CartOwnerContext = Depends(get_cart_owner),
    db: AsyncSession = Depends(get_db),
):
    result = await EcommerceCartService.update_quantity(db, owner, data.key, data.quantity)
    await db.commit()
    return result


@router.delete("/remove")
async def remove_from_cart(
    data: RemoveCartRequest,
    owner: CartOwnerContext = Depends(get_cart_owner),
    db: AsyncSession = Depends(get_db),
):
    message = await EcommerceCartService.remove_item(db, owner, data.key)
    await db.commit()
    return message


@router.delete("/remove-all")
async def remove_all_from_cart(
    owner: CartOwnerContext = Depends(get_cart_owner),
    db: AsyncSession = Depends(get_db),
):
    message = await EcommerceCartService.remove_all(db, owner)
    await db.commit()
    return message


@router.post("/select-cart-items")
async def select_cart_items(
    data: SelectCartItemsRequest,
    owner: CartOwnerContext = Depends(get_cart_owner),
    db: AsyncSession = Depends(get_db),
):
    message = await EcommerceCartService.select_items(db, owner, data.ids, data.action)
    await db.commit()
    return message
