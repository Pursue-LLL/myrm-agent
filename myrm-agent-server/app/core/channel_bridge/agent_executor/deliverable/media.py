"""Oversized deliverable media handling for channel IM outbound.

Single source of truth for the channel attachment size cap, plus a
Hermes-style progressive image compressor so oversized images still reach
users as attachments instead of being silently dropped.

[INPUT]
- None (self-contained; stdlib + Pillow only)

[OUTPUT]
- MAX_CHANNEL_ATTACHMENT_BYTES: shared attachment cap for artifact-event and path-scan delivery
- format_human_size: human-readable size string for user-facing notes
- is_compressible_image: whether a filename is a Pillow-compressible raster image
- compress_oversized_image: progressive compression producing a temp file under the cap

[POS]
Channel deliverable attachment cap + oversized-image fallback (Hermes parity).
Consumed by deliverable.deep_links.collect_channel_artifacts and
deliverable.scanner.collect_deliverable_paths_from_text.
"""

from __future__ import annotations

import io
import logging
import os
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

MAX_CHANNEL_ATTACHMENT_BYTES = 5 * 1024 * 1024

_COMPRESSIBLE_IMAGE_EXTS = frozenset({".png", ".jpg", ".jpeg", ".webp"})
_QUALITY_STEPS = (85, 70, 50)
_MAX_COMPRESSION_ROUNDS = 5
_MIN_DIMENSION = 64


def format_human_size(size_bytes: int) -> str:
    """Format a byte count as a human-readable size string (e.g. '600 B', '128 KB' or '8.2 MB')."""
    if size_bytes < 1024:
        return f"{max(size_bytes, 1)} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.0f} KB"
    return f"{size_bytes / (1024 * 1024):.1f} MB"


def is_compressible_image(filename: str) -> bool:
    """True when the filename extension is a Pillow-compressible raster image."""
    return Path(filename).suffix.lower() in _COMPRESSIBLE_IMAGE_EXTS


def compress_oversized_image(src: str | Path, *, max_bytes: int) -> Path | None:
    """Compress a raster image under ``max_bytes`` via progressive degradation.

    Mirrors Hermes ``vision_tools``: JPEG/WEBP quality descends 85 → 70 → 50,
    PNG only shrinks dimensions; dimensions are halved between rounds (min side
    64 px); RGBA/LA/P is flattened onto a white background for lossy output.
    Returns a new temp file path on success, or None when the image is not
    readable, not a supported format, or still exceeds the cap.
    """
    try:
        from PIL import Image
    except ImportError:
        logger.warning("Pillow unavailable — cannot compress oversized image %s", src)
        return None

    try:
        img = Image.open(src)
        img.load()
    except Exception:
        logger.warning("Pillow failed to open image for compression: %s", src)
        return None

    src_format = (img.format or "").upper()
    if src_format not in {"JPEG", "WEBP", "PNG"}:
        return None

    use_quality = src_format in {"JPEG", "WEBP"}
    if use_quality:
        if img.mode in {"RGBA", "LA", "P"}:
            rgba = img.convert("RGBA")
            background = Image.new("RGB", rgba.size, (255, 255, 255))
            background.paste(rgba, mask=rgba.getchannel("A"))
            img = background
        elif img.mode not in {"RGB", "L"}:
            img = img.convert("RGB")
    elif img.mode in {"P", "LA"}:
        img = img.convert("RGBA")
    elif img.mode not in {"RGBA", "RGB", "L"}:
        img = img.convert("RGB")

    out_format = "JPEG" if use_quality else "PNG"
    quality_steps = _QUALITY_STEPS if use_quality else (None,)

    for _ in range(_MAX_COMPRESSION_ROUNDS):
        for q in quality_steps:
            buf = io.BytesIO()
            save_kwargs = {"format": out_format}
            if q is not None:
                save_kwargs["quality"] = q
            try:
                img.save(buf, **save_kwargs)
            except Exception:
                continue
            if buf.tell() <= max_bytes:
                fd, tmp = tempfile.mkstemp(
                    suffix=".jpg" if use_quality else ".png",
                    prefix="deliverable_",
                )
                with os.fdopen(fd, "wb") as fh:
                    fh.write(buf.getvalue())
                return Path(tmp)

        new_w = max(img.width // 2, _MIN_DIMENSION)
        new_h = max(img.height // 2, _MIN_DIMENSION)
        if (new_w, new_h) == (img.width, img.height):
            break
        img = img.resize((new_w, new_h), Image.LANCZOS)

    return None
