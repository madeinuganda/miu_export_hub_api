from __future__ import annotations

import io

from PIL import Image

from app.core.shared.exceptions import AppError

_THUMB_MAX_EDGE = 256
_THUMB_JPEG_QUALITY = 82


def make_thumbnail(
    content: bytes,
    *,
    max_edge: int = _THUMB_MAX_EDGE,
    quality: int = _THUMB_JPEG_QUALITY,
) -> bytes:
    """Resize and compress image bytes into a JPEG thumbnail."""
    try:
        image = Image.open(io.BytesIO(content))
        image.load()
    except Exception as exc:
        raise AppError(400, "Invalid image file", "invalid_image") from exc

    if image.mode in ("RGBA", "LA", "P"):
        flattened = Image.new("RGB", image.size, (255, 255, 255))
        rgba = image.convert("RGBA")
        flattened.paste(rgba, mask=rgba.split()[-1])
        image = flattened
    elif image.mode != "RGB":
        image = image.convert("RGB")

    image.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    image.save(out, format="JPEG", optimize=True, quality=quality)
    return out.getvalue()
