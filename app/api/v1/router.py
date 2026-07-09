from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.export_hub import admin, auth, buyer, buyer_onboarding, public, supplier
from app.api.v1.shared import notifications
from app.api.v1.ecommerce.router import router as ecommerce_router
from app.api.v1.export_hub.router import router as export_hub_router
from app.api.v1.shared.platform import router as platform_router

api_router = APIRouter(prefix="/api/v1")

# Canonical platform-scoped routes
api_router.include_router(export_hub_router)
api_router.include_router(ecommerce_router)
api_router.include_router(platform_router, tags=["Shared · Platforms"])
api_router.include_router(notifications.router, tags=["Shared · Notifications"])

# Legacy Export Hub paths (backward compatible, hidden from OpenAPI)
api_router.include_router(auth.router, include_in_schema=False)
api_router.include_router(public.router, include_in_schema=False)
api_router.include_router(buyer_onboarding.router, include_in_schema=False)
api_router.include_router(buyer.router, include_in_schema=False)
api_router.include_router(supplier.router, include_in_schema=False)
api_router.include_router(admin.router, include_in_schema=False)
