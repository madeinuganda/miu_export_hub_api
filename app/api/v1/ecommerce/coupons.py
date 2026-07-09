from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ecommerce.deps import CartOwnerContext, get_cart_owner, require_customer_password_changed
from app.core.shared.database import get_db
from app.models.ecommerce.accounts import CustomerAccount
from app.services.ecommerce.coupon_service import EcommerceCouponService

router = APIRouter()


@router.get("/coupon/apply")
async def apply_coupon(
    code: str = Query(...),
    owner: CartOwnerContext = Depends(get_cart_owner),
    db: AsyncSession = Depends(get_db),
):
    """Validate coupon against checked cart — Laravel GET /coupon/apply parity."""
    return await EcommerceCouponService.apply(db, owner, code)


@router.get("/coupon/list")
async def list_coupons(
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(1, ge=1),
    account: CustomerAccount = Depends(require_customer_password_changed),
    db: AsyncSession = Depends(get_db),
):
    owner = CartOwnerContext(owner_id=account.id, is_guest=False)
    return await EcommerceCouponService.list_coupons(db, owner, limit=limit, offset=offset)


@router.get("/coupon/applicable-list")
async def applicable_coupons(
    account: CustomerAccount = Depends(require_customer_password_changed),
    db: AsyncSession = Depends(get_db),
):
    owner = CartOwnerContext(owner_id=account.id, is_guest=False)
    return await EcommerceCouponService.applicable_list(db, owner)


@router.get("/coupons/{shop_id}/seller-wise-coupons")
async def seller_wise_coupons(
    shop_id: UUID,
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(1, ge=1),
    db: AsyncSession = Depends(get_db),
):
    from datetime import date

    from sqlalchemy import func, select

    from app.models.ecommerce.promotions import EcommerceCoupon

    today = date.today()
    query = select(EcommerceCoupon).where(
        EcommerceCoupon.deleted_at.is_(None),
        EcommerceCoupon.is_active.is_(True),
        EcommerceCoupon.start_date <= today,
        EcommerceCoupon.expire_date >= today,
        EcommerceCoupon.shop_id == shop_id,
    )
    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar_one()
    page = max(offset, 1)
    coupons = (
        await db.execute(query.order_by(EcommerceCoupon.created_at.desc()).offset((page - 1) * limit).limit(limit))
    ).scalars().all()
    return {
        "total_size": total,
        "limit": limit,
        "offset": page,
        "coupons": [
            {
                "title": c.title,
                "code": c.code,
                "discount": float(c.discount),
                "discount_type": c.discount_type.value,
                "min_purchase": float(c.min_purchase),
            }
            for c in coupons
        ],
    }
