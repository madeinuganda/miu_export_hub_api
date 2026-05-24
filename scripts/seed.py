from __future__ import annotations

"""Seed database with demo data. Run: python -m scripts.seed"""
import asyncio
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal, Base, engine
from app.core.security import hash_password
from app.models import *  # noqa: F401, F403
from app.models.catalog import Category, Product, ProductBadge, ProductImage, ProductCertification, PlatformStat
from app.models.enums import (
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
from app.models.marketplace import (
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
from app.models.messaging import ConversationMessage, ConversationThread
from app.models.accounts import AdminAccount, BuyerAccount, BuyerNotification, BuyerPreference, SupplierAccount, SupplierNotification
from app.models.misc import ExportChecklistTemplate
from app.models.orders import Order, OrderActivity, OrderMilestone, OrderTracking
from app.models.organizations import BuyerOrganization, BuyerOrganizationMember, SupplierOrganization, SupplierOrganizationMember
from app.models.payments import PaymentEscrow, PaymentMilestone
from app.models.rfqs import Rfq, RfqQuote
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

        if (
            await db.execute(
                select(BuyerAccount).where(BuyerAccount.email == "hans.mueller@naturkost.de", BuyerAccount.deleted_at.is_(None))
            )
        ).scalar_one_or_none():
            await db.commit()
            print("Admin: admin@miu.ug / MIU@2026 (password synced). Demo data already present.")
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
        )
        apply_create_audit(buyer_org, buyer_account.id)
        db.add(buyer_org)
        await db.flush()
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

        await db.commit()
        print("Seed complete.")
        print("  Admin:    admin@miu.ug / MIU@2026")
        print("  Buyer:    hans.mueller@naturkost.de / Buyer123!")
        print("  Supplier: amara@rwenzoriorganics.ug / Supplier123!")


if __name__ == "__main__":
    asyncio.run(seed())
