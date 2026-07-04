from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.ecommerce import addresses, auth, cart, catalog, checkout, orders, seller, shipping

router = APIRouter(prefix="/ecommerce")

router.include_router(auth.router)
router.include_router(catalog.router)
router.include_router(cart.router)
router.include_router(checkout.router)
router.include_router(shipping.router)
router.include_router(orders.router)
router.include_router(addresses.router)
router.include_router(seller.router)
