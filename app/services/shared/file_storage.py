from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.shared.config import get_settings
from app.core.shared.exceptions import AppError
from app.models.export_hub.misc import FileRecord
from app.utils.audit import apply_create_audit


async def store_upload_file(
    db: AsyncSession,
    *,
    file: UploadFile,
    uploaded_by: UUID,
    subdirectory: str,
) -> FileRecord:
    settings = get_settings()
    content = await file.read()

    if not content:
        raise AppError(400, "Empty file", "empty_file")
    if len(content) > settings.max_upload_bytes:
        raise AppError(413, "File exceeds maximum size", "file_too_large")

    mime = file.content_type or "application/octet-stream"
    if mime not in settings.mime_allowlist:
        raise AppError(400, f"File type not allowed: {mime}", "invalid_mime")

    suffix = Path(file.filename or "upload").suffix.lower()
    if suffix not in {".pdf", ".jpg", ".jpeg", ".png", ".webp"}:
        raise AppError(400, "Invalid file extension", "invalid_extension")

    return await store_upload_bytes(
        db,
        content=content,
        mime_type=mime,
        suffix=suffix,
        uploaded_by=uploaded_by,
        subdirectory=subdirectory,
    )


async def store_upload_bytes(
    db: AsyncSession,
    *,
    content: bytes,
    mime_type: str,
    suffix: str,
    uploaded_by: UUID,
    subdirectory: str,
) -> FileRecord:
    settings = get_settings()
    if not content:
        raise AppError(400, "Empty file", "empty_file")
    if len(content) > settings.max_upload_bytes:
        raise AppError(413, "File exceeds maximum size", "file_too_large")

    storage_key = f"{subdirectory.strip('/')}/{uuid4().hex}{suffix}"
    dest = Path(settings.storage_path) / storage_key
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(content)

    record = FileRecord(
        storage_key=storage_key,
        mime_type=mime_type,
        size_bytes=len(content),
        uploaded_by=uploaded_by,
    )
    apply_create_audit(record, uploaded_by)
    db.add(record)
    await db.flush()
    return record


def public_file_url(storage_key: str) -> str:
    """Build a public path for a stored file.

    Paths are under ``/api/uploads`` so production reverse proxies that only
    forward ``/api`` (e.g. exporthub.miu.ug) still serve gallery/logo assets.
    """
    key = storage_key.lstrip("/")
    for prefix in ("api/uploads/", "uploads/"):
        if key.startswith(prefix):
            key = key[len(prefix) :]
            break
    return f"/api/uploads/{key}"


def as_public_file_url(url: str | None) -> str | None:
    """Normalize a stored image/document URL for API responses."""
    if url is None:
        return None
    trimmed = url.strip()
    if not trimmed:
        return trimmed

    if trimmed.startswith(("http://", "https://")):
        from urllib.parse import urlparse

        parsed = urlparse(trimmed)
        path = parsed.path or ""
        if path.startswith("/uploads/"):
            path = f"/api{path}"
        elif not path.startswith("/api/uploads/"):
            return trimmed
        query = f"?{parsed.query}" if parsed.query else ""
        return f"{path}{query}"

    if trimmed.startswith("/uploads/"):
        return f"/api{trimmed}"
    if trimmed.startswith("uploads/"):
        return f"/api/uploads/{trimmed[len('uploads/') :]}"
    if trimmed.startswith("/api/uploads/") or trimmed.startswith("api/uploads/"):
        return trimmed if trimmed.startswith("/") else f"/{trimmed}"
    return trimmed
