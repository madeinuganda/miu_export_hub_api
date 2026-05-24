"""Add action_required to supplier verification_status enum."""

from alembic import op

revision = "005_supplier_action_required"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TYPE verification_status ADD VALUE IF NOT EXISTS 'action_required'"
    )


def downgrade() -> None:
    # PostgreSQL does not support removing enum values safely.
    pass
