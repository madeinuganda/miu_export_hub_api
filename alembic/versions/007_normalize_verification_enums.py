"""Normalize verification enums to lowercase values matching Python enums."""

from alembic import op

revision = "007_normalize_verification_enums"
down_revision = "006_buyer_action_required"
branch_labels = None
depends_on = None

_LOWERCASE_VALUES = ("draft", "pending", "action_required", "approved", "rejected", "suspended")


def _normalize_enum(column: str, table: str, type_name: str) -> None:
    values_sql = ", ".join(f"'{v}'" for v in _LOWERCASE_VALUES)
    new_type = f"{type_name}_new"

    op.execute(f"ALTER TABLE {table} ALTER COLUMN {column} TYPE text USING {column}::text")
    op.execute(f"UPDATE {table} SET {column} = lower({column})")

    op.execute(f"CREATE TYPE {new_type} AS ENUM ({values_sql})")
    op.execute(
        f"ALTER TABLE {table} ALTER COLUMN {column} TYPE {new_type} "
        f"USING {column}::{new_type}"
    )
    op.execute(f"DROP TYPE {type_name}")
    op.execute(f"ALTER TYPE {new_type} RENAME TO {type_name}")


def upgrade() -> None:
    _normalize_enum("onboarding_status", "buyer_organizations", "buyer_onboarding_status")
    _normalize_enum("verification_status", "supplier_organizations", "verification_status")


def downgrade() -> None:
    # PostgreSQL cannot safely revert enum value renames.
    pass
