from __future__ import annotations

from app.models.shared.enums import Platform

# Export Hub — B2B trade assurance
EXPORT_HUB_PERMISSIONS: dict[str, str] = {
    "export_hub.rfqs.read": "View RFQs and deal pipeline",
    "export_hub.rfqs.manage": "Assign RFQs, relay quotes, manage deals",
    "export_hub.orders.read": "View export orders",
    "export_hub.orders.manage": "Advance pipeline, milestones, escrow release",
    "export_hub.verification.read": "View supplier/buyer verification",
    "export_hub.verification.manage": "Approve, reject, suspend applications",
    "export_hub.buyers.manage": "Manage export hub buyer organizations",
    "export_hub.suppliers.manage": "Manage export hub supplier organizations",
    "export_hub.categories.manage": "Manage product categories",
    "export_hub.cms.manage": "Manage export hub CMS content",
    "export_hub.admins.manage": "Invite and manage export hub admins",
}

EXPORT_HUB_ROLE_PERMISSIONS: dict[str, list[str]] = {
    "export_hub.super_admin": list(EXPORT_HUB_PERMISSIONS.keys()),
    "export_hub.trade_admin": [
        "export_hub.rfqs.read",
        "export_hub.rfqs.manage",
        "export_hub.orders.read",
        "export_hub.orders.manage",
        "export_hub.verification.read",
        "export_hub.verification.manage",
        "export_hub.buyers.manage",
        "export_hub.suppliers.manage",
        "export_hub.categories.manage",
    ],
    "export_hub.read_only": [
        "export_hub.rfqs.read",
        "export_hub.orders.read",
        "export_hub.verification.read",
    ],
}

# E-commerce — retail marketplace (Laravel parity target)
ECOMMERCE_PERMISSIONS: dict[str, str] = {
    "ecommerce.dashboard.view": "View admin dashboard and KPIs",
    "ecommerce.orders.manage": "Manage retail orders and fulfillment",
    "ecommerce.products.manage": "Manage catalog, stock, and approvals",
    "ecommerce.customers.manage": "Manage retail customers",
    "ecommerce.vendors.manage": "Manage sellers/vendors and shops",
    "ecommerce.promotions.manage": "Coupons, banners, deals, upsell",
    "ecommerce.pos.manage": "Point of sale (admin and vendor)",
    "ecommerce.reports.view": "Sales, stock, and transaction reports",
    "ecommerce.settings.manage": "Business settings and integrations",
    "ecommerce.admins.manage": "Invite and manage e-commerce admins",
}

ECOMMERCE_ROLE_PERMISSIONS: dict[str, list[str]] = {
    "ecommerce.super_admin": list(ECOMMERCE_PERMISSIONS.keys()),
    "ecommerce.operations": [
        "ecommerce.dashboard.view",
        "ecommerce.orders.manage",
        "ecommerce.products.manage",
        "ecommerce.customers.manage",
        "ecommerce.reports.view",
    ],
    "ecommerce.vendor_manager": [
        "ecommerce.dashboard.view",
        "ecommerce.vendors.manage",
        "ecommerce.products.manage",
        "ecommerce.orders.manage",
    ],
}

PLATFORM_PERMISSIONS: dict[Platform, dict[str, str]] = {
    Platform.EXPORT_HUB: EXPORT_HUB_PERMISSIONS,
    Platform.ECOMMERCE: ECOMMERCE_PERMISSIONS,
}

PLATFORM_ROLE_PERMISSIONS: dict[Platform, dict[str, list[str]]] = {
    Platform.EXPORT_HUB: EXPORT_HUB_ROLE_PERMISSIONS,
    Platform.ECOMMERCE: ECOMMERCE_ROLE_PERMISSIONS,
}
