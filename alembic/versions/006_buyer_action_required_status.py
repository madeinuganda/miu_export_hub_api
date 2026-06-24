"""Add action_required to buyer_onboarding_status enum."""

from alembic import op

revision = "006_buyer_action_required"
down_revision = "005_supplier_action_required"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TYPE buyer_onboarding_status ADD VALUE IF NOT EXISTS 'action_required'"
    )


def downgrade() -> None:
    # PostgreSQL does not support removing enum values safely.
    pass
