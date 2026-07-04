"""Platform RBAC, e-commerce accounts, and role assignments."""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

from migration_utils import table_exists

revision: str = "008_platform_rbac_ecommerce"
down_revision: Union[str, None] = "007_normalize_verification_enums"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    import app.models  # noqa: F401
    import app.models.ecommerce_accounts  # noqa: F401
    import app.models.rbac  # noqa: F401
    from app.core.shared.database import Base

    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)

    if table_exists("permissions"):
        from app.services.shared.rbac_service import seed_default_rbac_sync

        seed_default_rbac_sync(bind)


def downgrade() -> None:
    pass
