"""Render sample PDFs and HTML emails for visual review.

Usage: python scripts/preview_documents.py [output_dir]
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:  # Full app settings when the API deps are installed, stub otherwise.
    from app.core.shared.config import get_settings  # noqa: F401
except Exception:  # pragma: no cover - preview helper only
    stub = types.ModuleType("app.core.shared.config")

    class _Settings:
        frontend_base_url = "https://exporthub.miu.ug"
        password_reset_ttl_hours = 1
        environment = "development"

    stub.get_settings = lambda: _Settings()
    sys.modules.setdefault("app", types.ModuleType("app"))
    sys.modules.setdefault("app.core", types.ModuleType("app.core"))
    sys.modules.setdefault("app.core.shared", types.ModuleType("app.core.shared"))
    sys.modules["app.core.shared.config"] = stub

from app.services.shared.document_service import (  # noqa: E402
    order_document,
    payment_receipt_document,
    quotation_document,
    rfq_document,
)
from app.services.shared.notifications.email_templates import (  # noqa: E402
    Bullets,
    Button,
    Callout,
    Details,
    Paragraph,
    render_email,
)

BUYER = ["Nordic Coffee Roasters AB", "Sofia Lind", "Gothenburg, Sweden"]
SUPPLIER = ["Kigezi Highland Coffee Ltd", "Kabale, Uganda", "MIU verified supplier"]


def main() -> None:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "uploads" / "_previews")
    out.mkdir(parents=True, exist_ok=True)

    documents = [
        rfq_document(
            reference="RFQ-2418",
            issued_on="27 Aug 2026",
            buyer_lines=BUYER,
            supplier_lines=SUPPLIER,
            product_name="Arabica Green Beans, Screen 17/18",
            quantity_label="18,000 kg",
            destination="Gothenburg, Sweden",
            target_price="UGX 14,500 / kg",
            incoterm="FOB Mombasa",
            needed_by="15 Nov 2026",
            requirements="Organic certification required. Jute bags, 60kg each.",
        ),
        quotation_document(
            reference="RFQ-2418",
            quote_reference="QTN-2418-01",
            issued_on="27 Aug 2026",
            valid_until="26 Sep 2026",
            buyer_lines=BUYER,
            supplier_lines=SUPPLIER,
            product_name="Arabica Green Beans, Screen 17/18",
            quantity_label="18,000 kg",
            unit_price="UGX 14,900 / kg",
            total_price="UGX 268,200,000",
            incoterm="FOB Mombasa",
            lead_time="25 days",
            shipment_terms="One 20ft container, jute bags",
            notes="Price holds for 30 days. Organic certificate copies included.",
        ),
        order_document(
            reference="ORD-9042",
            issued_on="27 Aug 2026",
            status="Payment secured",
            buyer_lines=BUYER,
            supplier_lines=SUPPLIER,
            product_name="Arabica Green Beans, Screen 17/18",
            quantity_label="18,000 kg",
            unit_price="UGX 14,900 / kg",
            total_value="UGX 268,200,000",
            upfront="UGX 187,740,000",
            balance="UGX 80,460,000",
            incoterm="FOB Mombasa",
            lead_time="25 days",
            rfq_reference="RFQ-2418",
        ),
        payment_receipt_document(
            reference="POP-9042-01",
            order_reference="ORD-9042",
            issued_on="27 Aug 2026",
            payment_type_label="Down payment",
            amount="UGX 187,740,000",
            method="Bank transfer",
            payment_reference="SWIFT 88213-AC",
            paid_at="26 Aug 2026",
            buyer_lines=BUYER,
            supplier_lines=SUPPLIER,
            product_name="Arabica Green Beans, Screen 17/18",
            order_total="UGX 268,200,000",
            note="70% down payment received and held in escrow.",
        ),
    ]

    for attachment in documents:
        if attachment is None:
            print("PDF generation unavailable (fpdf2 missing)")
            continue
        target = out / attachment.filename
        target.write_bytes(attachment.content)
        print(f"{target}  ({len(attachment.content):,} bytes)")

    email = render_email(
        subject="Quote received for RFQ-2418",
        heading="Your quote is ready",
        eyebrow="Quote received",
        greeting="Hi Sofia,",
        blocks=[
            Paragraph("A quote reviewed by the MIU trade desk is ready for your RFQ."),
            Details(
                title="Quote summary",
                rows=[
                    ("RFQ", "RFQ-2418"),
                    ("Product", "Arabica Green Beans, Screen 17/18"),
                    ("Offered price", "UGX 14,900 / kg"),
                ],
            ),
            Callout("Price holds for 30 days.", title="Supplier notes"),
            Bullets(items=["Escrow protected", "MIU verified supplier"]),
            Button("Review and accept", "https://exporthub.miu.ug/dashboard/buyer/rfqs"),
            Paragraph("The full quotation is attached as a PDF.", muted=True),
        ],
    )
    (out / "email-quote-received.html").write_text(email.html, encoding="utf-8")
    (out / "email-quote-received.txt").write_text(email.text, encoding="utf-8")
    print(out / "email-quote-received.html")


if __name__ == "__main__":
    main()
