"""Media input clamping and resilience guard for image and video tools.

[INPUT]
- bytes (raw input image payload)
- PIL.Image, PIL.ImageOps (Pillow image processing library)

[OUTPUT]
- clamp_image_payload(): sanitize, transpose, downsample and format-normalize image bytes

[POS]
Production-grade image sanitizer preventing HTTP 413 Payload Too Large, RGBA JPEG crashes,
and EXIF rotation issues before passing payloads to downstream vision/generation engines.
"""

from __future__ import annotations

import io
import logging
from typing import Final

from PIL import Image, ImageOps, UnidentifiedImageError

logger = logging.getLogger(__name__)

DEFAULT_MAX_DIMENSION: Final[int] = 2048
DEFAULT_MAX_BYTES: Final[int] = 4 * 1024 * 1024  # 4 MB
DEFAULT_JPEG_QUALITY: Final[int] = 85
_EXIF_ORIENTATION_TAG: Final[int] = 0x0112


def _has_exif_rotation(img: Image.Image) -> bool:
    """Check whether image has an active EXIF orientation tag requiring rotation."""
    try:
        exif = img.getexif()
        if exif:
            orientation = exif.get(_EXIF_ORIENTATION_TAG)
            return orientation is not None and orientation not in (0, 1)
    except (AttributeError, ValueError, OSError):
        pass
    return False


def _composite_alpha_on_white(img: Image.Image) -> Image.Image:
    """Blend transparent image over a clean white background into standard 3-channel RGB."""
    rgba_img = img.convert("RGBA")
    background = Image.new("RGB", rgba_img.size, (255, 255, 255))
    background.paste(rgba_img, mask=rgba_img.split()[3])
    return background


def clamp_image_payload(
    data: bytes,
    *,
    content_type: str | None = None,
    max_dimension: int = DEFAULT_MAX_DIMENSION,
    max_bytes: int = DEFAULT_MAX_BYTES,
    quality: int = DEFAULT_JPEG_QUALITY,
) -> tuple[bytes, str, int]:
    """Sanitize, auto-transpose, resize and normalize image bytes.

    Returns:
        tuple of (sanitized_bytes, mime_type, byte_length).
    """
    if not data:
        return data, content_type or "image/jpeg", 0

    try:
        with Image.open(io.BytesIO(data)) as raw_img:
            has_alpha = raw_img.mode in ("RGBA", "LA") or (
                raw_img.mode == "P" and "transparency" in raw_img.info
            )
            needs_rotation = _has_exif_rotation(raw_img)
            needs_dimension_clamp = max(raw_img.width, raw_img.height) > max_dimension
            needs_byte_clamp = len(data) > max_bytes

            # Lossless bypass: return exact bytes if image already satisfies all criteria
            if (
                not needs_rotation
                and not has_alpha
                and not needs_dimension_clamp
                and not needs_byte_clamp
            ):
                resolved_mime = content_type or (
                    f"image/{raw_img.format.lower()}"
                    if raw_img.format
                    else "image/jpeg"
                )
                return data, resolved_mime, len(data)

            # 1. Physical orientation baking
            working_img = ImageOps.exif_transpose(raw_img) if needs_rotation else raw_img.copy()

            # 2. Alpha compositing to RGB
            if has_alpha:
                working_img = _composite_alpha_on_white(working_img)
            elif working_img.mode != "RGB":
                working_img = working_img.convert("RGB")

            # 3. Proportional downsampling
            if max(working_img.width, working_img.height) > max_dimension:
                working_img.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)

            # 4. Save to optimized JPEG
            out_buf = io.BytesIO()
            working_img.save(
                out_buf,
                format="JPEG",
                quality=quality,
                optimize=True,
            )
            clamped_bytes = out_buf.getvalue()
            return clamped_bytes, "image/jpeg", len(clamped_bytes)

    except (UnidentifiedImageError, OSError, ValueError, Exception) as exc:
        logger.warning("Image downsample guard skipped due to decode error: %s", exc)
        return data, content_type or "image/jpeg", len(data)
