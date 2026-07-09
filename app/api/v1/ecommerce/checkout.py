from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ecommerce.deps import CartOwnerContext, get_cart_owner
from app.core.shared.database import get_db
from app.services.ecommerce.cart_service import EcommerceCartService

router = APIRouter(prefix="/checkout")


@router.get("/preview")
async def checkout_preview(
    owner: CartOwnerContext = Depends(get_cart_owner),
    db: AsyncSession = Depends(get_db),
):
    """Order preview from checked cart items with shipping and payment options."""
    return await EcommerceCartService.checkout_preview(db, owner)
