from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ecommerce.deps import CartOwnerContext, get_cart_owner
from app.core.shared.database import get_db
from app.schemas.ecommerce.address import (
    ShippingAddressCreateRequest,
    ShippingAddressDeleteRequest,
    ShippingAddressResponse,
    ShippingAddressUpdateRequest,
)
from app.services.ecommerce.address_service import EcommerceAddressService

router = APIRouter(prefix="/customer/address", tags=["E-Commerce · Addresses"])


@router.get("/list", response_model=list[ShippingAddressResponse])
async def address_list(
    owner: CartOwnerContext = Depends(get_cart_owner),
    db: AsyncSession = Depends(get_db),
):
    return await EcommerceAddressService.list_addresses(db, owner)


@router.post("/add")
async def add_address(
    data: ShippingAddressCreateRequest,
    owner: CartOwnerContext = Depends(get_cart_owner),
    db: AsyncSession = Depends(get_db),
):
    result = await EcommerceAddressService.add_address(db, owner, data)
    await db.commit()
    return result


@router.post("/update")
async def update_address(
    data: ShippingAddressUpdateRequest,
    owner: CartOwnerContext = Depends(get_cart_owner),
    db: AsyncSession = Depends(get_db),
):
    result = await EcommerceAddressService.update_address(db, owner, data)
    await db.commit()
    return result


@router.delete("/")
async def delete_address(
    data: ShippingAddressDeleteRequest,
    owner: CartOwnerContext = Depends(get_cart_owner),
    db: AsyncSession = Depends(get_db),
):
    result = await EcommerceAddressService.delete_address(db, owner, data.address_id)
    await db.commit()
    return result
