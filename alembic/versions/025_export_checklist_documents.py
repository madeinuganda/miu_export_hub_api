"""Add export_checklist_documents table for per-item document uploads."""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "025_export_checklist_documents"
down_revision: Union[str, None] = "024_export_checklist_seed_items"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    import app.models  # noqa: F401  (registers all models, incl. ExportChecklistDocument, on Base.metadata)
    from app.core.shared.database import Base

    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    pass
