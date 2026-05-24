from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import AppError
from app.models.misc import FileRecord
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

    storage_key = f"{subdirectory.strip('/')}/{uuid4().hex}{suffix}"
    dest = Path(settings.storage_path) / storage_key
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(content)

    record = FileRecord(
        storage_key=storage_key,
        mime_type=mime,
        size_bytes=len(content),
        uploaded_by=uploaded_by,
    )
    apply_create_audit(record, uploaded_by)
    db.add(record)
    await db.flush()
    return record
