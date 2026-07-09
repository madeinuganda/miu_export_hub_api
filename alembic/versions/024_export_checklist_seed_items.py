"""Align export checklist templates with the supplier-facing 16-item checklist."""

from __future__ import annotations

import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "024_export_checklist_seed_items"
down_revision: Union[str, None] = "022_rfq_message_moderation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (section_id, item_key, title, description, required) — mirrors the frontend's
# src/data/supplierExportChecklist.ts so item_key/section_id line up 1:1.
CANONICAL_ITEMS: list[tuple[str, str, str, str, bool]] = [
    ("business", "cert-incorporation", "Certificate of Incorporation", "Issued by URSB — must be valid and not expired", True),
    ("business", "tin", "Tax Identification Number (TIN)", "URA-issued TIN certificate", True),
    ("business", "vat", "VAT Registration (if applicable)", "Required if annual turnover exceeds UGX 150M", False),
    ("quality", "unbs", "UNBS Quality Mark Certificate", "Cross-checked against UNBS registry. Photos alone are not accepted", True),
    ("quality", "made-in-uganda", "Made-in-Uganda Registration", "Certificate from MTIC confirming local origin", True),
    ("quality", "haccp", "HACCP Compliance Certificate", "Required for processed food exports to EU", True),
    ("quality", "iso22000", "ISO 22000 (Food Safety Management)", "Strongly recommended for EU and US markets", False),
    ("export-docs", "export-license", "Export License", "Issued by Ministry of Trade — required for all exports", True),
    ("export-docs", "phytosanitary", "Phytosanitary Certificate", "Issued by MAARD — required for agricultural products", True),
    ("export-docs", "cert-origin", "Certificate of Origin", "Chamber of Commerce — confirms Ugandan origin", False),
    ("export-docs", "fumigation", "Fumigation Certificate", "Required for certain commodities and destinations", False),
    ("product-testing", "lab-results", "Third-Party Lab Test Results", "Microbial and heavy-metal screening for food exports", False),
    ("product-testing", "moisture-test", "Moisture Content Certificate", "Required for dried agricultural products", False),
    ("product-testing", "pesticide-residue", "Pesticide Residue Report", "EU MRL compliance for coffee, vanilla, and herbs", False),
    ("labelling", "export-label", "Export Label Design Approved", "Labels must include product name, weight, origin, allergens, expiry", True),
    ("labelling", "packaging-spec", "Packaging Specifications", "Export-grade packaging meeting buyer and transit requirements", True),
]


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "export_checklist_templates" not in insp.get_table_names():
        return

    meta = sa.MetaData()
    templates = sa.Table("export_checklist_templates", meta, autoload_with=bind)

    canonical_keys = {item_key for _, item_key, *_ in CANONICAL_ITEMS}

    # Soft-delete old placeholder items that predate the real checklist content
    # (business_license, export_permit, invoice_template).
    bind.execute(
        templates.update()
        .where(
            sa.and_(
                templates.c.item_key.notin_(canonical_keys),
                templates.c.deleted_at.is_(None),
            )
        )
        .values(deleted_at=sa.func.now())
    )

    existing_keys = {
        row[0]
        for row in bind.execute(
            sa.select(templates.c.item_key).where(templates.c.deleted_at.is_(None))
        )
    }

    rows = [
        {
            "id": uuid.uuid4(),
            "section_id": section_id,
            "item_key": item_key,
            "title": title,
            "description": description,
            "required": required,
            "version": 1,
        }
        for section_id, item_key, title, description, required in CANONICAL_ITEMS
        if item_key not in existing_keys
    ]
    if rows:
        bind.execute(templates.insert(), rows)


def downgrade() -> None:
    pass
