from __future__ import annotations

"""Seed database with demo data. Run: python -m scripts.seed"""
import asyncio
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.shared.database import AsyncSessionLocal, Base, engine
from app.core.shared.security import hash_password
from app.models import *  # noqa: F401, F403
from app.models.export_hub.catalog import Category, Product, ProductBadge, ProductImage, ProductCertification, PlatformStat
from app.models.shared.enums import (
    ConversationType,
    EscrowStatus,
    MilestoneState,
    OrderStatus,
    OrgMemberRole,
    PaymentMilestoneStatus,
    ProductStatus,
    QuoteStatus,
    RfqStatus,
    SenderRole,
    StockStatus,
    VerificationStatus,
)
from app.models.export_hub.marketplace import (
    CmsFeature,
    CmsFeaturedProduct,
    CmsHero,
    CmsHowItWorksStep,
    CmsNavLink,
    CmsSiteSettings,
    CmsSupplierHero,
    CmsTestimonial,
    CmsTradeCta,
    CmsTrustItem,
)
from app.models.export_hub.messaging import ConversationMessage, ConversationThread
from app.models.export_hub.accounts import AdminAccount, BuyerAccount, BuyerNotification, BuyerPreference, SupplierAccount, SupplierNotification
from app.models.export_hub.misc import ExportChecklistTemplate
from app.models.export_hub.orders import Order, OrderActivity, OrderMilestone, OrderTracking
from app.models.export_hub.organizations import BuyerOrganization, BuyerOrganizationMember, SupplierOrganization, SupplierOrganizationMember
from app.models.export_hub.payments import PaymentEscrow, PaymentMilestone
from app.models.export_hub.rfqs import Rfq, RfqQuote
from app.utils.audit import apply_create_audit


async def ensure_seed_admin(db: AsyncSession) -> AdminAccount:
    admin = (
        await db.execute(select(AdminAccount).where(AdminAccount.email == "admin@miu.ug", AdminAccount.deleted_at.is_(None)))
    ).scalar_one_or_none()
    if admin:
        admin.password_hash = hash_password("MIU@2026")
        admin.must_change_password = False
        admin.is_active = True
        return admin
    admin = AdminAccount(
        email="admin@miu.ug",
        password_hash=hash_password("MIU@2026"),
        first_name="MIU",
        last_name="Admin",
        is_active=True,
        email_verified_at=datetime.now(timezone.utc),
        must_change_password=False,
    )
    apply_create_audit(admin, admin.id)
    db.add(admin)
    await db.flush()
    return admin


async def seed() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as db:
        admin = await ensure_seed_admin(db)
        from app.services.shared.rbac_service import seed_default_rbac

        await seed_default_rbac(db)

        if (
            await db.execute(
                select(BuyerAccount).where(BuyerAccount.email == "hans.mueller@naturkost.de", BuyerAccount.deleted_at.is_(None))
            )
        ).scalar_one_or_none():
            await seed_ecommerce_accounts(db, admin)
            await seed_ecommerce_catalog(db, admin)
            await db.commit()
            print("Admin: admin@miu.ug / MIU@2026 (password synced). Demo data already present.")
            print("  E-Commerce Admin:    shop-admin@miu.ug / ShopAdmin123!")
            print("  E-Commerce Customer: shop@example.com / Customer123!")
            return

        buyer_account = BuyerAccount(
            email="hans.mueller@naturkost.de",
            password_hash=hash_password("Buyer123!"),
            first_name="Hans",
            last_name="Müller",
            phone="+49 30 123456",
            is_active=True,
            email_verified_at=datetime.now(timezone.utc),
        )
        apply_create_audit(buyer_account, buyer_account.id)
        db.add(buyer_account)
        await db.flush()

        buyer_org = BuyerOrganization(
            name="Naturkost GmbH",
            country="Germany",
            city="Berlin",
            industry="Organic Food Retail",
            onboarding_status=VerificationStatus.APPROVED,
            verified_buyer=True,
            onboarding_submitted_at=datetime.now(timezone.utc),
            procurement_contact="Hans Müller",
            job_title="Procurement Director",
            website="https://naturkost.de",
        )
        apply_create_audit(buyer_org, buyer_account.id)
        db.add(buyer_org)
        await db.flush()

        pending_buyer_account = BuyerAccount(
            email="pending.buyer@example.com",
            password_hash=buyer_account.password_hash,
            first_name="Amina",
            last_name="Nakato",
            phone="+256 700 000 001",
            is_active=True,
            email_verified_at=datetime.now(timezone.utc),
        )
        apply_create_audit(pending_buyer_account, buyer_account.id)
        db.add(pending_buyer_account)
        await db.flush()

        pending_buyer_org = BuyerOrganization(
            name="Kampala Fresh Imports Ltd",
            country="Uganda",
            city="Kampala",
            industry="Food & Beverage",
            onboarding_status=VerificationStatus.PENDING,
            verified_buyer=False,
            onboarding_submitted_at=datetime.now(timezone.utc),
            procurement_contact="Amina Nakato",
            job_title="Head of Procurement",
        )
        apply_create_audit(pending_buyer_org, buyer_account.id)
        db.add(pending_buyer_org)
        await db.flush()
        db.add(
            BuyerOrganizationMember(
                org_id=pending_buyer_org.id,
                buyer_account_id=pending_buyer_account.id,
                role=OrgMemberRole.OWNER,
                created_by=buyer_account.id,
                updated_by=buyer_account.id,
            )
        )
        db.add(
            BuyerRegistrationDraft(
                buyer_account_id=pending_buyer_account.id,
                step="review",
                payload={
                    "company": {
                        "company_name": "Kampala Fresh Imports Ltd",
                        "country": "Uganda",
                        "city": "Kampala",
                        "industry": "Food & Beverage",
                    },
                    "contact": {"contact_name": "Amina Nakato", "job_title": "Head of Procurement"},
                    "sourcing": {
                        "categories": ["Coffee", "Vanilla"],
                        "target_markets": ["EU", "UK"],
                        "annual_import_volume": "500-1000 MT",
                    },
                },
                created_by=buyer_account.id,
                updated_by=buyer_account.id,
            )
        )
        db.add(
            BuyerOrganizationMember(
                org_id=buyer_org.id,
                buyer_account_id=buyer_account.id,
                role=OrgMemberRole.OWNER,
                created_by=buyer_account.id,
                updated_by=buyer_account.id,
            )
        )
        db.add(
            BuyerPreference(
                buyer_account_id=buyer_account.id,
                language="de",
                timezone="Europe/Berlin",
                currency_display="UGX",
                created_by=buyer_account.id,
                updated_by=buyer_account.id,
            )
        )

        supplier_account = SupplierAccount(
            email="amara@rwenzoriorganics.ug",
            password_hash=hash_password("Supplier123!"),
            first_name="Amara",
            last_name="Nakato",
            phone="+256 700 123456",
            is_active=True,
            email_verified_at=datetime.now(timezone.utc),
        )
        apply_create_audit(supplier_account, supplier_account.id)
        db.add(supplier_account)
        await db.flush()

        supplier_org = SupplierOrganization(
            name="Rwenzori Organics Ltd",
            slug="rwenzori-organics",
            business_type="Exporter",
            category="Coffee & Tea",
            region="Western",
            district="Kasese",
            tagline="Premium organic exports from the Rwenzori foothills",
            verification_status=VerificationStatus.APPROVED,
            approved_at=datetime.now(timezone.utc),
            storefront_published=True,
        )
        apply_create_audit(supplier_org, supplier_account.id)
        db.add(supplier_org)
        await db.flush()
        db.add(
            SupplierOrganizationMember(
                org_id=supplier_org.id,
                supplier_account_id=supplier_account.id,
                role=OrgMemberRole.OWNER,
                created_by=supplier_account.id,
                updated_by=supplier_account.id,
            )
        )

        elgon = SupplierOrganization(
            name="Elgon Coffee Exporters Ltd",
            slug="elgon-coffee",
            category="Coffee & Tea",
            region="Eastern",
            district="Mbale",
            verification_status=VerificationStatus.APPROVED,
            approved_at=datetime.now(timezone.utc),
            storefront_published=True,
        )
        apply_create_audit(elgon, admin.id)
        db.add(elgon)
        await db.flush()

        pending_supplier_account = SupplierAccount(
            email="miriam@pearltextile.ug",
            password_hash=hash_password("Supplier123!"),
            first_name="Miriam",
            last_name="Nakato",
            phone="+256 700 555 123",
            is_active=True,
            email_verified_at=datetime.now(timezone.utc),
        )
        apply_create_audit(pending_supplier_account, pending_supplier_account.id)
        db.add(pending_supplier_account)
        await db.flush()

        pending_supplier_org = SupplierOrganization(
            name="Pearl Textile Weavers Co.",
            slug="pearl-textile",
            business_type="Manufacturer",
            category="Apparel & Textiles",
            region="Eastern",
            district="Jinja",
            verification_status=VerificationStatus.PENDING,
            storefront_published=False,
        )
        apply_create_audit(pending_supplier_org, pending_supplier_account.id)
        db.add(pending_supplier_org)
        await db.flush()
        db.add(
            SupplierOrganizationMember(
                org_id=pending_supplier_org.id,
                supplier_account_id=pending_supplier_account.id,
                role=OrgMemberRole.OWNER,
                created_by=pending_supplier_account.id,
                updated_by=pending_supplier_account.id,
            )
        )

        cats = [
            Category(slug="coffee", label="Coffee & Tea", sort_order=1, is_active=True, created_by=admin.id, updated_by=admin.id),
            Category(slug="spices", label="Spices & Herbs", sort_order=2, is_active=True, created_by=admin.id, updated_by=admin.id),
            Category(slug="oils", label="Oils & Fats", sort_order=3, is_active=True, created_by=admin.id, updated_by=admin.id),
        ]
        db.add_all(cats)
        await db.flush()

        coffee = Product(
            supplier_org_id=elgon.id,
            sku="PRD-001",
            name="Single-Origin Arabica Coffee Beans — Mt. Elgon AA Grade",
            category_id=cats[0].id,
            subcategory="Coffee & Tea",
            description="Premium single-origin Arabica from Mt. Elgon slopes.",
            origin_story="Grown at 1800–2200m by smallholder farmers.",
            status=ProductStatus.PUBLISHED,
            moq_value=Decimal("500"),
            moq_unit="kg",
            price_amount=Decimal("16650"),
            lead_time_days=21,
            stock_status=StockStatus.IN_STOCK,
            trade_assurance_note="70% upfront",
            sample_available=True,
            tone="coffee",
            rating=Decimal("5.0"),
            review_count=127,
            created_by=admin.id,
            updated_by=admin.id,
        )
        db.add(coffee)
        await db.flush()
        db.add(ProductImage(product_id=coffee.id, url="https://images.unsplash.com/photo-1447933601403-0c6688de566e?w=800&h=600&fit=crop", is_primary=True, sort_order=0, created_by=admin.id, updated_by=admin.id))
        db.add(ProductBadge(product_id=coffee.id, badge="verified", created_by=admin.id, updated_by=admin.id))
        db.add(ProductCertification(product_id=coffee.id, certification_name="Organic", created_by=admin.id, updated_by=admin.id))

        vanilla = Product(
            supplier_org_id=supplier_org.id,
            sku="PRD-S004",
            name="Organic Vanilla Beans — Grade A Export",
            subcategory="Spices & Herbs",
            status=ProductStatus.PUBLISHED,
            moq_value=Decimal("50"),
            moq_unit="kg",
            price_amount=Decimal("166500"),
            stock_status=StockStatus.IN_STOCK,
            tone="vanilla",
            created_by=supplier_account.id,
            updated_by=supplier_account.id,
        )
        db.add(vanilla)
        await db.flush()

        db.add(
            CmsHero(
                eyebrow="Made in Uganda",
                title="Connect with verified Ugandan exporters",
                subtitle="B2B marketplace with MIU Trade Assurance",
                cta_primary_label="Browse Products",
                cta_primary_url="/browse",
                cta_secondary_label="Become a Supplier",
                cta_secondary_url="/register/supplier",
                background_image_url="https://images.unsplash.com/photo-1442512595335-e89e73853f31?w=1600",
                is_active=True,
                created_by=admin.id,
                updated_by=admin.id,
            )
        )
        db.add(CmsSiteSettings(announcement_text="🌍 New buyers from 12 countries joined this month", phone="+256 800 MIU", email="hello@miu.ug", footer_links={"about": "/about", "contact": "/contact"}, created_by=admin.id, updated_by=admin.id))
        db.add(CmsTrustItem(icon="shield", title="Trade Assurance", body="70/30 escrow protection", sort_order=0, created_by=admin.id, updated_by=admin.id))
        db.add(CmsFeaturedProduct(product_id=coffee.id, sort_order=0, created_by=admin.id, updated_by=admin.id))
        db.add(CmsHowItWorksStep(step_number=1, title="Browse", body="Discover verified products", icon="search", created_by=admin.id, updated_by=admin.id))
        db.add(CmsFeature(title="Verified Suppliers", body="Every supplier vetted by MIU", icon="badge", sort_order=0, created_by=admin.id, updated_by=admin.id))
        db.add(CmsTestimonial(quote="MIU transformed our sourcing.", author="Hans Müller", role="Procurement Director", company="Naturkost GmbH", country="Germany", sort_order=0, created_by=admin.id, updated_by=admin.id))
        db.add(CmsTradeCta(title="Start exporting today", body="Join 800+ verified suppliers", button_label="Register", button_url="/register/supplier", created_by=admin.id, updated_by=admin.id))
        db.add(CmsSupplierHero(title="Grow your export business", body="Reach global buyers", cta_label="Apply Now", cta_url="/register/supplier", created_by=admin.id, updated_by=admin.id))
        db.add(CmsNavLink(label="Browse", href="/browse", sort_order=0, created_by=admin.id, updated_by=admin.id))
        db.add(PlatformStat(key="countries", headline="48", subtext="Countries reached", icon_key="globe", sort_order=0, created_by=admin.id, updated_by=admin.id))

        for section, items in [
            ("registration", [("business_license", "Business License"), ("export_permit", "Export Permit")]),
            ("documentation", [("invoice_template", "Commercial Invoice Template")]),
        ]:
            for key, title in items:
                db.add(ExportChecklistTemplate(section_id=section, item_key=key, title=title, required=True, created_by=admin.id, updated_by=admin.id))

        rfq_new = Rfq(
            public_id="RFQ-2026-0042",
            buyer_org_id=buyer_org.id,
            product_id=vanilla.id,
            supplier_org_id=supplier_org.id,
            quantity=Decimal("5000"),
            unit="kg",
            target_price_amount=Decimal("12000"),
            destination_port="Stockholm, Sweden",
            message="Looking for consistent monthly supply with 99.9% purity certificate.",
            status=RfqStatus.AWAITING,
            sent_at=datetime.now(timezone.utc) - timedelta(days=2),
            created_by=buyer_account.id,
            updated_by=admin.id,
        )
        db.add(rfq_new)
        await db.flush()

        rfq1 = Rfq(
            public_id="RFQ-2026-001",
            buyer_org_id=buyer_org.id,
            product_id=coffee.id,
            supplier_org_id=elgon.id,
            quantity=Decimal("2000"),
            unit="kg",
            target_price_amount=Decimal("16650"),
            destination_port="Hamburg, Germany",
            status=RfqStatus.RESPONDED,
            sent_at=datetime.now(timezone.utc) - timedelta(days=5),
            created_by=buyer_account.id,
            updated_by=buyer_account.id,
        )
        db.add(rfq1)
        await db.flush()
        db.add(
            RfqQuote(
                rfq_id=rfq1.id,
                supplier_org_id=elgon.id,
                unit_price=Decimal("16095"),
                incoterm="CIF",
                lead_time_days=21,
                notes="We can supply 2,000 kg from our current harvest. CIF Hamburg.",
                status=QuoteStatus.SENT,
                sent_at=datetime.now(timezone.utc) - timedelta(days=3),
                created_by=supplier_account.id,
                updated_by=supplier_account.id,
            )
        )

        order = Order(
            public_id="MIU-ORD-2026-001",
            buyer_org_id=buyer_org.id,
            supplier_org_id=elgon.id,
            product_id=coffee.id,
            rfq_id=rfq1.id,
            quantity=Decimal("2000"),
            unit="kg",
            total_value_amount=Decimal("32190000"),
            status=OrderStatus.SHIPPED,
            tone="coffee",
            created_by=buyer_account.id,
            updated_by=buyer_account.id,
        )
        db.add(order)
        await db.flush()
        admin_steps = [
            ("confirmed", "Confirmed"),
            ("payment_secured", "Payment Secured"),
            ("in_production", "In Production"),
            ("ready_to_dispatch", "Ready to Dispatch"),
            ("shipped", "Shipped"),
            ("delivered", "Delivered"),
            ("fulfilled", "Fulfilled"),
        ]
        shipped_index = 4
        for i, (key, label) in enumerate(admin_steps):
            state = MilestoneState.COMPLETE if i < shipped_index else MilestoneState.CURRENT if i == shipped_index else MilestoneState.UPCOMING
            db.add(
                OrderMilestone(
                    order_id=order.id,
                    step_key=key,
                    label=label,
                    state=state,
                    sort_order=i,
                    created_by=admin.id,
                    updated_by=admin.id,
                )
            )
        db.add(OrderActivity(order_id=order.id, occurred_at=datetime.now(timezone.utc), description="Shipment departed Mombasa port.", created_by=admin.id, updated_by=admin.id))
        db.add(OrderTracking(order_id=order.id, tracking_number="MSKU1234567", carrier="Maersk", eta_date=date.today() + timedelta(days=14), created_by=admin.id, updated_by=admin.id))
        escrow = PaymentEscrow(order_id=order.id, total_amount=Decimal("32190000"), upfront_amount=Decimal("22533000"), balance_amount=Decimal("9657000"), status=EscrowStatus.UPFRONT_RECEIVED, created_by=admin.id, updated_by=admin.id)
        db.add(escrow)

        buyer_thread = ConversationThread(thread_type=ConversationType.BUYER_MIU, buyer_org_id=buyer_org.id, subject="MIU Account Manager", created_by=buyer_account.id, updated_by=buyer_account.id)
        db.add(buyer_thread)
        await db.flush()
        db.add(ConversationMessage(thread_id=buyer_thread.id, sender_role=SenderRole.ADMIN, body="Welcome to MIU! Your account manager is here to help.", sent_at=datetime.now(timezone.utc), created_by=admin.id, updated_by=admin.id))

        db.add(
            BuyerNotification(
                buyer_account_id=buyer_account.id,
                type="rfq",
                title="Supplier responded",
                body="Quote received for RFQ-2026-001",
                icon_key="message",
                created_by=admin.id,
                updated_by=admin.id,
            )
        )
        db.add(
            SupplierNotification(
                supplier_account_id=supplier_account.id,
                type="rfq",
                title="New RFQ received",
                body="1,000 kg Arabica Coffee Beans",
                icon_key="message",
                created_by=admin.id,
                updated_by=admin.id,
            )
        )

        await seed_ecommerce_accounts(db, admin)
        await seed_ecommerce_catalog(db, admin)
        await db.commit()
        print("Seed complete.")
        print("  Export Hub Admin:  admin@miu.ug / MIU@2026")
        print("  Export Hub Buyer:    hans.mueller@naturkost.de / Buyer123!")
        print("  Export Hub Supplier: amara@rwenzoriorganics.ug / Supplier123!")
        print("  E-Commerce Admin:    shop-admin@miu.ug / ShopAdmin123!")
        print("  E-Commerce Customer: shop@example.com / Customer123!")


async def seed_ecommerce_accounts(db: AsyncSession, actor: AdminAccount) -> None:
    from app.models.ecommerce.accounts import CustomerAccount, EcommerceAdminAccount
    from app.models.shared.enums import CustomerType, EcommerceAccountType, Platform
    from app.models.shared.rbac import AccountRoleAssignment, Role

    if (
        await db.execute(
            select(EcommerceAdminAccount).where(
                EcommerceAdminAccount.email == "shop-admin@miu.ug",
                EcommerceAdminAccount.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none():
        return

    ecommerce_admin = EcommerceAdminAccount(
        email="shop-admin@miu.ug",
        password_hash=hash_password("ShopAdmin123!"),
        first_name="Shop",
        last_name="Admin",
        is_active=True,
        email_verified_at=datetime.now(timezone.utc),
    )
    apply_create_audit(ecommerce_admin, actor.id)
    db.add(ecommerce_admin)
    await db.flush()

    role = (
        await db.execute(
            select(Role).where(
                Role.platform == Platform.ECOMMERCE,
                Role.code == "ecommerce.super_admin",
                Role.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if role:
        db.add(
            AccountRoleAssignment(
                platform=Platform.ECOMMERCE,
                account_type=EcommerceAccountType.ADMIN.value,
                account_id=ecommerce_admin.id,
                role_id=role.id,
                created_by=actor.id,
                updated_by=actor.id,
            )
        )

    shop_customer = CustomerAccount(
        email="shop@example.com",
        password_hash=hash_password("Customer123!"),
        first_name="Shop",
        last_name="Customer",
        customer_type=CustomerType.SHOP,
        is_active=True,
        email_verified_at=datetime.now(timezone.utc),
    )
    apply_create_audit(shop_customer, actor.id)
    db.add(shop_customer)

    retail_customer = CustomerAccount(
        email="retail@example.com",
        password_hash=hash_password("Customer123!"),
        first_name="Retail",
        last_name="Customer",
        customer_type=CustomerType.RETAIL,
        is_active=True,
        email_verified_at=datetime.now(timezone.utc),
    )
    apply_create_audit(retail_customer, actor.id)
    db.add(retail_customer)


async def seed_ecommerce_catalog(db: AsyncSession, actor: AdminAccount) -> None:
    from decimal import Decimal

    from app.models.ecommerce.accounts import EcommerceShop, SellerAccount
    from app.models.ecommerce.catalog import (
        EcommerceBanner,
        EcommerceBrand,
        EcommerceCategory,
        EcommerceProduct,
        EcommerceProductImage,
    )
    from app.models.shared.enums import (
        EcommerceBannerResourceType,
        EcommerceCategoryPosition,
        EcommerceDiscountType,
        EcommerceProductStatus,
        StockStatus,
    )

    if (
        await db.execute(
            select(EcommerceProduct).where(EcommerceProduct.deleted_at.is_(None)).limit(1)
        )
    ).scalar_one_or_none():
        return

    seller = SellerAccount(
        email="vendor@miu.ug",
        password_hash=hash_password("Seller123!"),
        first_name="Uganda",
        last_name="Vendor",
        is_active=True,
        email_verified_at=datetime.now(timezone.utc),
    )
    apply_create_audit(seller, actor.id)
    db.add(seller)
    await db.flush()

    shop = EcommerceShop(
        seller_account_id=seller.id,
        name="Kampala Fresh Market",
        slug="kampala-fresh",
        tagline="Quality Ugandan goods for your shop",
        is_published=True,
    )
    apply_create_audit(shop, actor.id)
    db.add(shop)
    await db.flush()

    root_cat = EcommerceCategory(
        name="Packaged Foods",
        slug="packaged-foods",
        position=EcommerceCategoryPosition.ROOT,
        priority=10,
        home_status=True,
    )
    apply_create_audit(root_cat, actor.id)
    db.add(root_cat)
    await db.flush()

    sub_cat = EcommerceCategory(
        name="Snacks",
        slug="snacks",
        parent_id=root_cat.id,
        position=EcommerceCategoryPosition.SUB,
        priority=5,
        home_status=True,
    )
    apply_create_audit(sub_cat, actor.id)
    db.add(sub_cat)
    await db.flush()

    brand = EcommerceBrand(name="MIU Select", slug="miu-select", is_active=True)
    apply_create_audit(brand, actor.id)
    db.add(brand)
    await db.flush()

    products = [
        EcommerceProduct(
            shop_id=shop.id,
            name="Roasted Groundnut Snack 500g",
            code="SNK-001",
            slug="roasted-groundnut-snack-500g",
            category_id=root_cat.id,
            sub_category_id=sub_cat.id,
            brand_id=brand.id,
            unit_price=Decimal("8500"),
            discount=Decimal("10"),
            discount_type=EcommerceDiscountType.PERCENT,
            thumbnail_url="https://images.unsplash.com/photo-1599599810769-0c5e0b0a0a0a?w=400",
            details="Crunchy roasted groundnuts — perfect for retail shelves.",
            status=EcommerceProductStatus.PUBLISHED,
            featured=True,
            current_stock=500,
            stock_status=StockStatus.IN_STOCK,
            average_review=Decimal("4.5"),
            reviews_count=12,
        ),
        EcommerceProduct(
            shop_id=shop.id,
            name="Uganda Coffee Beans 1kg",
            code="BEV-001",
            slug="uganda-coffee-beans-1kg",
            category_id=root_cat.id,
            brand_id=brand.id,
            unit_price=Decimal("45000"),
            discount=Decimal("0"),
            discount_type=EcommerceDiscountType.PERCENT,
            thumbnail_url="https://images.unsplash.com/photo-1559056199-641a0ac8b55e?w=400",
            details="Premium Arabica coffee beans from Rwenzori region.",
            status=EcommerceProductStatus.PUBLISHED,
            featured=True,
            current_stock=120,
            stock_status=StockStatus.IN_STOCK,
            average_review=Decimal("4.8"),
            reviews_count=34,
        ),
        EcommerceProduct(
            shop_id=shop.id,
            name="Mango Dried Fruit 250g",
            code="SNK-002",
            slug="mango-dried-fruit-250g",
            category_id=root_cat.id,
            sub_category_id=sub_cat.id,
            brand_id=brand.id,
            unit_price=Decimal("12000"),
            discount=Decimal("1500"),
            discount_type=EcommerceDiscountType.FLAT,
            thumbnail_url="https://images.unsplash.com/photo-1605027990121-475fd60a326f?w=400",
            details="Naturally dried Ugandan mango slices.",
            status=EcommerceProductStatus.PUBLISHED,
            featured=False,
            current_stock=200,
            stock_status=StockStatus.IN_STOCK,
            average_review=Decimal("4.2"),
            reviews_count=8,
        ),
    ]
    for p in products:
        apply_create_audit(p, actor.id)
        db.add(p)
    await db.flush()

    for p in products:
        db.add(
            EcommerceProductImage(
                product_id=p.id,
                url=p.thumbnail_url or "",
                is_primary=True,
                sort_order=0,
                created_by=actor.id,
                updated_by=actor.id,
            )
        )

    featured = products[0]
    db.add(
        EcommerceBanner(
            title="Shop Ugandan Snacks",
            sub_title="Wholesale prices for your store",
            button_text="Shop Now",
            photo_url=featured.thumbnail_url or "",
            background_color="#1a5632",
            url=f"/products/details/{featured.slug}",
            resource_type=EcommerceBannerResourceType.PRODUCT,
            resource_id=featured.id,
            is_published=True,
            sort_order=0,
            created_by=actor.id,
            updated_by=actor.id,
        )
    )


if __name__ == "__main__":
    asyncio.run(seed())
