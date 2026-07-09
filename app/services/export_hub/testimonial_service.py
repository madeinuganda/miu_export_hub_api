from __future__ import annotations

from pathlib import Path
from uuid import UUID

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.shared.config import get_settings
from app.core.shared.exceptions import AppError
from app.models.export_hub.accounts import AdminAccount
from app.models.export_hub.marketplace import CmsTestimonial
from app.schemas.export_hub.testimonial import (
    PublicTestimonialItem,
    PublicTestimonialListResponse,
    TestimonialCreate,
    TestimonialItem,
    TestimonialListResponse,
    TestimonialUpdate,
)
from app.services.shared.file_storage import public_file_url, store_upload_bytes
from app.utils.audit import apply_create_audit, apply_update_audit, soft_delete


def _author_initial(author: str) -> str:
    trimmed = author.strip()
    return trimmed[0].upper() if trimmed else "?"


class TestimonialService:
    @staticmethod
    def _to_item(testimonial: CmsTestimonial) -> TestimonialItem:
        role_type = testimonial.role_type if testimonial.role_type in {"supplier", "buyer"} else "supplier"
        return TestimonialItem(
            id=testimonial.id,
            quote=testimonial.quote,
            author=testimonial.author,
            company=testimonial.company,
            detail=testimonial.detail or testimonial.country,
            role_type=role_type,
            metric=testimonial.metric,
            rating=testimonial.rating or 5,
            avatar_url=testimonial.avatar_url,
            sort_order=testimonial.sort_order,
            is_active=testimonial.is_active,
            created_at=testimonial.created_at,
            updated_at=testimonial.updated_at,
        )

    @staticmethod
    def _to_public_item(testimonial: CmsTestimonial) -> PublicTestimonialItem:
        role_type = testimonial.role_type if testimonial.role_type in {"supplier", "buyer"} else "supplier"
        return PublicTestimonialItem(
            id=testimonial.id,
            quote=testimonial.quote,
            name=testimonial.author,
            company=testimonial.company,
            detail=testimonial.detail or testimonial.country,
            roleType=role_type,
            metric=testimonial.metric,
            rating=testimonial.rating or 5,
            avatarUrl=testimonial.avatar_url,
            initial=_author_initial(testimonial.author),
        )

    @staticmethod
    async def list_testimonials(
        db: AsyncSession,
        *,
        active_only: bool = False,
    ) -> TestimonialListResponse:
        query = select(CmsTestimonial).where(CmsTestimonial.deleted_at.is_(None))
        if active_only:
            query = query.where(CmsTestimonial.is_active.is_(True))
        query = query.order_by(CmsTestimonial.sort_order, CmsTestimonial.created_at)
        rows = (await db.execute(query)).scalars().all()
        items = [TestimonialService._to_item(row) for row in rows]
        return TestimonialListResponse(items=items, total=len(items))

    @staticmethod
    async def list_public_testimonials(db: AsyncSession) -> PublicTestimonialListResponse:
        rows = (
            await db.execute(
                select(CmsTestimonial)
                .where(CmsTestimonial.is_active.is_(True), CmsTestimonial.deleted_at.is_(None))
                .order_by(CmsTestimonial.sort_order, CmsTestimonial.created_at)
            )
        ).scalars().all()
        return PublicTestimonialListResponse(
            items=[TestimonialService._to_public_item(row) for row in rows],
        )

    @staticmethod
    async def get_testimonial(db: AsyncSession, testimonial_id: UUID) -> TestimonialItem:
        testimonial = await db.get(CmsTestimonial, testimonial_id)
        if not testimonial or testimonial.deleted_at:
            raise AppError(404, "Testimonial not found", "not_found")
        return TestimonialService._to_item(testimonial)

    @staticmethod
    async def create_testimonial(
        db: AsyncSession,
        admin: AdminAccount,
        data: TestimonialCreate,
    ) -> TestimonialItem:
        testimonial = CmsTestimonial(
            quote=data.quote.strip(),
            author=data.author.strip(),
            company=data.company.strip() if data.company else None,
            detail=data.detail.strip() if data.detail else None,
            role_type=data.role_type,
            metric=data.metric.strip() if data.metric else None,
            rating=data.rating,
            avatar_url=data.avatar_url,
            sort_order=data.sort_order,
            is_active=data.is_active,
        )
        apply_create_audit(testimonial, admin.id)
        db.add(testimonial)
        await db.flush()
        await db.refresh(testimonial)
        return TestimonialService._to_item(testimonial)

    @staticmethod
    async def update_testimonial(
        db: AsyncSession,
        admin: AdminAccount,
        testimonial_id: UUID,
        data: TestimonialUpdate,
    ) -> TestimonialItem:
        testimonial = await db.get(CmsTestimonial, testimonial_id)
        if not testimonial or testimonial.deleted_at:
            raise AppError(404, "Testimonial not found", "not_found")

        updates = data.model_dump(exclude_unset=True)
        if "quote" in updates and updates["quote"] is not None:
            testimonial.quote = updates["quote"].strip()
        if "author" in updates and updates["author"] is not None:
            testimonial.author = updates["author"].strip()
        if "company" in updates:
            testimonial.company = updates["company"].strip() if updates["company"] else None
        if "detail" in updates:
            testimonial.detail = updates["detail"].strip() if updates["detail"] else None
        if "role_type" in updates and updates["role_type"] is not None:
            testimonial.role_type = updates["role_type"]
        if "metric" in updates:
            testimonial.metric = updates["metric"].strip() if updates["metric"] else None
        if "rating" in updates and updates["rating"] is not None:
            testimonial.rating = updates["rating"]
        if "sort_order" in updates and updates["sort_order"] is not None:
            testimonial.sort_order = updates["sort_order"]
        if "is_active" in updates and updates["is_active"] is not None:
            testimonial.is_active = updates["is_active"]
        if "avatar_url" in updates:
            testimonial.avatar_url = updates["avatar_url"]

        apply_update_audit(testimonial, admin.id)
        await db.flush()
        await db.refresh(testimonial)
        return TestimonialService._to_item(testimonial)

    @staticmethod
    async def upload_avatar(
        db: AsyncSession,
        admin: AdminAccount,
        testimonial_id: UUID,
        file: UploadFile,
    ) -> TestimonialItem:
        testimonial = await db.get(CmsTestimonial, testimonial_id)
        if not testimonial or testimonial.deleted_at:
            raise AppError(404, "Testimonial not found", "not_found")

        content = await file.read()
        if not content:
            raise AppError(400, "Empty file", "empty_file")

        mime = file.content_type or "application/octet-stream"
        suffix = Path(file.filename or "upload").suffix.lower()
        if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
            raise AppError(400, "Invalid file extension", "invalid_extension")

        settings = get_settings()
        if mime not in settings.mime_allowlist:
            raise AppError(400, f"File type not allowed: {mime}", "invalid_mime")
        if len(content) > settings.max_upload_bytes:
            raise AppError(413, "File exceeds maximum size", "file_too_large")

        record = await store_upload_bytes(
            db,
            content=content,
            mime_type=mime,
            suffix=suffix,
            uploaded_by=admin.id,
            subdirectory="testimonials",
        )
        await db.refresh(testimonial)
        testimonial.avatar_url = public_file_url(record.storage_key)
        apply_update_audit(testimonial, admin.id)
        await db.flush()
        await db.refresh(testimonial)
        return TestimonialService._to_item(testimonial)

    @staticmethod
    async def delete_testimonial(
        db: AsyncSession,
        admin: AdminAccount,
        testimonial_id: UUID,
        *,
        hard: bool = False,
    ) -> dict:
        testimonial = await db.get(CmsTestimonial, testimonial_id)
        if not testimonial or testimonial.deleted_at:
            raise AppError(404, "Testimonial not found", "not_found")

        if hard:
            await db.delete(testimonial)
        else:
            soft_delete(testimonial, admin.id)
        await db.flush()
        return {"ok": True, "id": str(testimonial_id)}
