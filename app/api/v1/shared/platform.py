from __future__ import annotations

from fastapi import APIRouter

from app.schemas.ecommerce.auth import PlatformInfo, PlatformsResponse
from app.models.shared.enums import EcommerceAccountType, ExportHubAccountType, Platform

router = APIRouter(prefix="/platforms")


@router.get("", response_model=PlatformsResponse)
async def list_platforms() -> PlatformsResponse:
    return PlatformsResponse(
        platforms=[
            PlatformInfo(
                id=Platform.EXPORT_HUB.value,
                name="Export Hub",
                description="B2B export marketplace — buyers, suppliers, trade assurance, RFQs",
                account_types=[
                    ExportHubAccountType.BUYER.value,
                    ExportHubAccountType.SUPPLIER.value,
                    ExportHubAccountType.ADMIN.value,
                ],
            ),
            PlatformInfo(
                id=Platform.ECOMMERCE.value,
                name="E-Commerce",
                description="Retail marketplace — customers, sellers, cart, checkout, POS",
                account_types=[
                    EcommerceAccountType.CUSTOMER.value,
                    EcommerceAccountType.SELLER.value,
                    EcommerceAccountType.ADMIN.value,
                    EcommerceAccountType.DELIVERY.value,
                ],
            ),
        ]
    )
