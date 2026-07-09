from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.ecommerce import (
    addresses,
    admin,
    admin_catalog,
    auth,
    cart,
    catalog,
    checkout,
    coupons,
    customer_extras,
    orders,
    seller,
    shipping,
    wallet,
)

router = APIRouter(prefix="/ecommerce")

router.include_router(auth.router, tags=["E-Commerce · Auth"])
router.include_router(catalog.router, tags=["E-Commerce · Catalog"])
router.include_router(cart.router, tags=["E-Commerce · Cart"])
router.include_router(checkout.router, tags=["E-Commerce · Checkout"])
router.include_router(shipping.router, tags=["E-Commerce · Shipping"])
router.include_router(orders.router, tags=["E-Commerce · Orders"])
router.include_router(coupons.router, tags=["E-Commerce · Coupons"])
router.include_router(wallet.router, tags=["E-Commerce · Wallet"])
router.include_router(addresses.router, tags=["E-Commerce · Addresses"])
router.include_router(seller.router, tags=["E-Commerce · Seller"])
router.include_router(admin.router, tags=["E-Commerce · Admin"])
router.include_router(admin_catalog.router, tags=["E-Commerce · Admin"])
router.include_router(customer_extras.router, tags=["E-Commerce · Reviews & Notifications"])
