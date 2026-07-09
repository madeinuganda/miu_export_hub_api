from __future__ import annotations

import re
from pathlib import Path
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi import UploadFile

from app.core.shared.config import get_settings
from app.core.shared.exceptions import AppError
from app.models.export_hub.accounts import AdminAccount
from app.models.export_hub.catalog import Category, Product
from app.schemas.export_hub.catalog import CategoryCreate, CategoryItem, CategoryListResponse, CategoryUpdate
from app.services.shared.file_storage import public_file_url, store_upload_bytes
from app.services.shared.image_processing import make_thumbnail
from app.utils.audit import apply_create_audit, apply_update_audit, soft_delete


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower().strip())
    return slug.strip("-")[:64] or "category"


class CategoryService:
    @staticmethod
    async def _unique_slug(db: AsyncSession, base: str, *, exclude_id: UUID | None = None) -> str:
        root = _slugify(base)
        candidate = root
        suffix = 2
        while True:
            query = select(Category).where(Category.slug == candidate, Category.deleted_at.is_(None))
            if exclude_id:
                query = query.where(Category.id != exclude_id)
            if (await db.execute(query)).scalar_one_or_none() is None:
                return candidate
            candidate = f"{root}-{suffix}"[:64]
            suffix += 1

    @staticmethod
    async def _validate_parent(db: AsyncSession, parent_id: UUID | None, category_id: UUID | None = None) -> None:
        if parent_id is None:
            return
        if category_id and parent_id == category_id:
            raise AppError(400, "Category cannot be its own parent", "invalid_parent")
        parent = await db.get(Category, parent_id)
        if not parent or parent.deleted_at:
            raise AppError(404, "Parent category not found", "not_found")

    @staticmethod
    async def _product_count(db: AsyncSession, category_id: UUID) -> int:
        return int(
            (
                await db.execute(
                    select(func.count())
                    .select_from(Product)
                    .where(Product.category_id == category_id, Product.deleted_at.is_(None))
                )
            ).scalar()
            or 0
        )

    @staticmethod
    async def _child_count(db: AsyncSession, category_id: UUID) -> int:
        return int(
            (
                await db.execute(
                    select(func.count())
                    .select_from(Category)
                    .where(Category.parent_id == category_id, Category.deleted_at.is_(None))
                )
            ).scalar()
            or 0
        )

    @staticmethod
    async def _to_item(db: AsyncSession, category: Category) -> CategoryItem:
        return CategoryItem(
            id=category.id,
            slug=category.slug,
            label=category.label,
            description=category.description,
            parent_id=category.parent_id,
            sort_order=category.sort_order,
            is_active=category.is_active,
            featured=category.featured,
            image_url=category.image_url,
            thumb_url=category.thumb_url,
            product_count=await CategoryService._product_count(db, category.id),
            child_count=await CategoryService._child_count(db, category.id),
            created_at=category.created_at,
            updated_at=category.updated_at,
        )

    @staticmethod
    async def list_categories(db: AsyncSession, *, active_only: bool = False) -> CategoryListResponse:
        query = select(Category).where(Category.deleted_at.is_(None)).order_by(Category.sort_order, Category.label)
        if active_only:
            query = query.where(Category.is_active.is_(True))
        categories = (await db.execute(query)).scalars().all()
        items = [await CategoryService._to_item(db, c) for c in categories]
        return CategoryListResponse(items=items, total=len(items))

    @staticmethod
    async def get_category(db: AsyncSession, category_id: UUID) -> CategoryItem:
        category = await db.get(Category, category_id)
        if not category or category.deleted_at:
            raise AppError(404, "Category not found", "not_found")
        return await CategoryService._to_item(db, category)

    @staticmethod
    async def create_category(db: AsyncSession, admin: AdminAccount, data: CategoryCreate) -> CategoryItem:
        await CategoryService._validate_parent(db, data.parent_id)
        slug = data.slug.strip() if data.slug else await CategoryService._unique_slug(db, data.label)
        if (await db.execute(select(Category).where(Category.slug == slug, Category.deleted_at.is_(None)))).scalar_one_or_none():
            raise AppError(409, "Category slug already exists", "slug_exists")

        category = Category(
            slug=slug,
            label=data.label.strip(),
            description=data.description,
            parent_id=data.parent_id,
            sort_order=data.sort_order,
            is_active=data.is_active,
            featured=data.featured,
            image_url=data.image_url,
            thumb_url=data.thumb_url,
        )
        apply_create_audit(category, admin.id)
        db.add(category)
        await db.flush()
        await db.refresh(category)
        return await CategoryService._to_item(db, category)

    @staticmethod
    async def update_category(
        db: AsyncSession, admin: AdminAccount, category_id: UUID, data: CategoryUpdate
    ) -> CategoryItem:
        category = await db.get(Category, category_id)
        if not category or category.deleted_at:
            raise AppError(404, "Category not found", "not_found")

        updates = data.model_dump(exclude_unset=True)
        if "parent_id" in updates:
            await CategoryService._validate_parent(db, updates["parent_id"], category_id)

        if "slug" in updates and updates["slug"] is not None:
            slug = updates["slug"].strip()
            existing = (
                await db.execute(
                    select(Category).where(
                        Category.slug == slug,
                        Category.deleted_at.is_(None),
                        Category.id != category_id,
                    )
                )
            ).scalar_one_or_none()
            if existing:
                raise AppError(409, "Category slug already exists", "slug_exists")
            category.slug = slug

        if "label" in updates and updates["label"] is not None:
            category.label = updates["label"].strip()
        if "description" in updates:
            category.description = updates["description"]
        if "parent_id" in updates:
            category.parent_id = updates["parent_id"]
        if "sort_order" in updates and updates["sort_order"] is not None:
            category.sort_order = updates["sort_order"]
        if "is_active" in updates and updates["is_active"] is not None:
            category.is_active = updates["is_active"]
        if "featured" in updates and updates["featured"] is not None:
            category.featured = updates["featured"]
        if "image_url" in updates:
            category.image_url = updates["image_url"]
        if "thumb_url" in updates:
            category.thumb_url = updates["thumb_url"]

        apply_update_audit(category, admin.id)
        await db.flush()
        await db.refresh(category)
        return await CategoryService._to_item(db, category)

    @staticmethod
    async def upload_category_image(
        db: AsyncSession,
        admin: AdminAccount,
        category_id: UUID,
        file: UploadFile,
        *,
        kind: str,
    ) -> CategoryItem:
        if kind not in {"image", "thumb"}:
            raise AppError(400, "Invalid image kind", "invalid_kind")

        category = await db.get(Category, category_id)
        if not category or category.deleted_at:
            raise AppError(404, "Category not found", "not_found")

        content = await file.read()
        if not content:
            raise AppError(400, "Empty file", "empty_file")

        mime = file.content_type or "application/octet-stream"
        suffix = Path(file.filename or "upload").suffix.lower()
        if suffix not in {".pdf", ".jpg", ".jpeg", ".png", ".webp"}:
            raise AppError(400, "Invalid file extension", "invalid_extension")

        settings = get_settings()
        if mime not in settings.mime_allowlist:
            raise AppError(400, f"File type not allowed: {mime}", "invalid_mime")
        if len(content) > settings.max_upload_bytes:
            raise AppError(413, "File exceeds maximum size", "file_too_large")

        should_auto_thumb = kind == "image" and not category.thumb_url and mime.startswith("image/")

        record = await store_upload_bytes(
            db,
            content=content,
            mime_type=mime,
            suffix=suffix,
            uploaded_by=admin.id,
            subdirectory="categories",
        )
        # store_upload_bytes flushes the session, which expires other loaded instances.
        await db.refresh(category)
        url = public_file_url(record.storage_key)
        if kind == "image":
            category.image_url = url
            if should_auto_thumb:
                try:
                    thumb_bytes = make_thumbnail(content)
                    thumb_record = await store_upload_bytes(
                        db,
                        content=thumb_bytes,
                        mime_type="image/jpeg",
                        suffix=".jpg",
                        uploaded_by=admin.id,
                        subdirectory="categories/thumbs",
                    )
                    await db.refresh(category)
                    category.thumb_url = public_file_url(thumb_record.storage_key)
                except AppError:
                    # Keep the main image even if thumbnail generation fails.
                    pass
        else:
            category.thumb_url = url

        apply_update_audit(category, admin.id)
        await db.flush()
        await db.refresh(category)
        return await CategoryService._to_item(db, category)

    @staticmethod
    async def delete_category(db: AsyncSession, admin: AdminAccount, category_id: UUID, *, hard: bool = False) -> dict:
        category = await db.get(Category, category_id)
        if not category or category.deleted_at:
            raise AppError(404, "Category not found", "not_found")

        if await CategoryService._child_count(db, category_id) > 0:
            raise AppError(409, "Remove or reassign child categories first", "has_children")
        if await CategoryService._product_count(db, category_id) > 0:
            raise AppError(409, "Reassign products before deleting this category", "has_products")

        if hard:
            # Hard delete category record once we are sure there are no dependants.
            await db.delete(category)
        else:
            soft_delete(category, admin.id)
        await db.flush()
        return {"ok": True, "id": str(category_id)}
