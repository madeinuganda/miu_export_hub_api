from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession


def apply_create_audit(entity: object, user_id: UUID | None) -> None:
    if hasattr(entity, "created_by"):
        entity.created_by = user_id  # type: ignore[attr-defined]
    if hasattr(entity, "updated_by"):
        entity.updated_by = user_id  # type: ignore[attr-defined]


def apply_update_audit(entity: object, user_id: UUID | None) -> None:
    if hasattr(entity, "updated_by"):
        entity.updated_by = user_id  # type: ignore[attr-defined]
    if hasattr(entity, "version"):
        entity.version = (entity.version or 1) + 1  # type: ignore[attr-defined]


def soft_delete(entity: object, user_id: UUID | None) -> None:
    entity.deleted_at = datetime.now(timezone.utc)  # type: ignore[attr-defined]
    entity.deleted_by = user_id  # type: ignore[attr-defined]


async def next_public_id(db: AsyncSession, prefix: str, table, column) -> str:
    from sqlalchemy import func, select

    year = datetime.now(timezone.utc).year
    pattern = f"{prefix}-{year}-%"
    result = await db.execute(select(func.count()).select_from(table).where(column.like(pattern)))
    count = (result.scalar() or 0) + 1
    return f"{prefix}-{year}-{count:03d}"
