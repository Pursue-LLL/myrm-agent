"""[INPUT]
- myrm_agent_harness.utils.chat_utils / image_utils / json_parsing (POS: framework primitives)
- app.core.utils.files_utils::read_image_as_base64 (POS: image read helper)

[OUTPUT]
- _degrade_old_images / _needs_compression_base64 / _compress_base64_image.

[POS]
Chat helper module: image degradation and inline compression helpers.
"""

from __future__ import annotations

import logging

from langchain_core.messages import BaseMessage, HumanMessage
from myrm_agent_harness.utils.image_utils import (
    content_has_images,
    strip_images_from_content,
)
from myrm_agent_harness.utils.media.image_compressor import MAX_DECODE_PIXELS

logger = logging.getLogger(__name__)

_INLINE_COMPRESS_THRESHOLD = 5 * 1024 * 1024


def _degrade_old_images(messages: list[BaseMessage], max_image_turns: int) -> None:
    """Replace images in older turns with text placeholders (in-place).

    Traverses messages from newest to oldest. Only the most recent
    max_image_turns HumanMessages with images keep their original content;
    older ones get their images stripped.
    """
    image_turns_seen = 0
    for i in range(len(messages) - 1, -1, -1):
        msg = messages[i]
        if not isinstance(msg, HumanMessage):
            continue
        if not content_has_images(msg.content):
            continue

        image_turns_seen += 1
        if image_turns_seen > max_image_turns:
            msg.content = strip_images_from_content(msg.content)


def _needs_compression_base64(b64_data: str, byte_size: int) -> bool:
    """Check if base64 image needs compression based on size or resolution."""
    if byte_size > _INLINE_COMPRESS_THRESHOLD:
        return True
    import base64
    import io

    try:
        from PIL import Image

        Image.MAX_IMAGE_PIXELS = MAX_DECODE_PIXELS
        raw_bytes = base64.b64decode(b64_data)
        with Image.open(io.BytesIO(raw_bytes)) as img:
            w, h = img.size
            return w > 4096 or h > 4096
    except Exception as e:
        logger.debug("Failed to check channel image resolution: %s", e)
        return False


def _compress_base64_image(b64_data: str) -> str | None:
    """Compress a base64-encoded image to JPEG with max 4096px dimension.

    Returns compressed base64 string or None if compression fails.
    """
    import base64
    import io

    try:
        from PIL import Image, ImageOps

        Image.MAX_IMAGE_PIXELS = MAX_DECODE_PIXELS
        raw_bytes = base64.b64decode(b64_data)
        img = Image.open(io.BytesIO(raw_bytes))
        img = ImageOps.exif_transpose(img)
        w, h = img.size
        max_dim = 4096
        if w > max_dim or h > max_dim:
            ratio = min(max_dim / w, max_dim / h)
            img = img.resize((int(w * ratio), int(h * ratio)), Image.Resampling.LANCZOS)

        if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
            img = img.convert("RGBA")
            bg = Image.new("RGB", img.size, (255, 255, 255))
            bg.paste(img, mask=img.split()[3])
            img = bg
        elif img.mode != "RGB":
            img = img.convert("RGB")

        out = io.BytesIO()
        img.save(out, format="JPEG", quality=80, optimize=True)
        compressed = out.getvalue()
        logger.info(
            "Channel image compressed: %dKB -> %dKB",
            len(raw_bytes) // 1024,
            len(compressed) // 1024,
        )
        return base64.b64encode(compressed).decode("ascii")
    except Exception as e:
        logger.warning("Channel image compression failed: %s", e)
    return None
