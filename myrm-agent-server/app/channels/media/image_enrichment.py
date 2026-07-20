"""Image attachment enrichment for channel inbound messages.

Detects image attachments in InboundMessage, downloads and compresses them,
saves to a local cache directory, and stores file path references in message
metadata so the business layer can build native multimodal queries.

The harness MediaResolverProcessor lazily resolves these file paths to base64
right before sending to the LLM, keeping checkpoints and message history lean.

Follows the same enrichment pattern as ``sticker_vision.describe_sticker_inbound``
and ``video_enrichment.enrich_video_inbound``: a pure async function that
enriches an InboundMessage, called from Router._handle_merged.

[INPUT]
- channels.types::InboundMessage, MediaType, MediaAttachment (POS: inbound message types)

[OUTPUT]
- has_image_attachment(): check for image media
- enrich_image_inbound(): download, compress, cache images as files into metadata

[POS]
Image attachment data preparation for channel router.
Stores file path references in ``msg.metadata["image_data_list"]`` for
downstream multimodal query construction in the business layer.
"""

from __future__ import annotations

import asyncio
import base64
import dataclasses
import hashlib
import io
import logging
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from app.channels.types import InboundMessage, MediaType

if TYPE_CHECKING:
    from app.channels.core.base import BaseChannel
    from app.channels.types import MediaAttachment

type GetChannelFn = Callable[[str], BaseChannel | None]

logger = logging.getLogger(__name__)

MAX_IMAGES_PER_MESSAGE = 4
COMPRESS_QUALITY = 0.7
MAX_DIMENSION_PX = 1568
MAX_IMAGE_BYTES = 5 * 1024 * 1024
DOWNLOAD_TIMEOUT = 15.0


def has_image_attachment(msg: InboundMessage) -> bool:
    """Check if the message contains at least one image attachment."""
    return any(a.media_type == MediaType.IMAGE for a in msg.media)


async def enrich_image_inbound(
    msg: InboundMessage,
    get_channel_fn: GetChannelFn | None,
) -> InboundMessage:
    """Enrich an InboundMessage with image data.

    Downloads image attachments, compresses them, caches as local files,
    and stores file path references in ``msg.metadata["image_data_list"]``.
    Falls back to inline base64 when caching fails.

    Returns the original message unchanged if no image attachments or
    all downloads fail (graceful degradation).
    """
    image_attachments = [a for a in msg.media if a.media_type == MediaType.IMAGE]
    if not image_attachments:
        return msg

    selected = image_attachments[:MAX_IMAGES_PER_MESSAGE]
    if len(image_attachments) > MAX_IMAGES_PER_MESSAGE:
        logger.warning(
            "Image enrichment: capped %d images to %d for %s/%s",
            len(image_attachments),
            MAX_IMAGES_PER_MESSAGE,
            msg.channel,
            msg.sender_id,
        )

    tasks = [_download_and_cache(att, msg, get_channel_fn) for att in selected]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    image_data_list: list[dict[str, str]] = []
    for idx, result in enumerate(results):
        if isinstance(result, Exception):
            logger.warning(
                "Image enrichment: download failed for image %d (%s/%s): %s",
                idx + 1,
                msg.channel,
                msg.sender_id,
                result,
            )
            continue
        if result is not None:
            image_data_list.append(result)

    if not image_data_list:
        return msg

    new_metadata = dict(msg.metadata)
    new_metadata["image_data_list"] = image_data_list

    logger.info(
        "Image enrichment: %d/%d image(s) prepared for %s/%s",
        len(image_data_list),
        len(selected),
        msg.channel,
        msg.sender_id,
    )
    return dataclasses.replace(msg, metadata=new_metadata)


async def _download_and_cache(
    att: MediaAttachment,
    msg: InboundMessage,
    get_channel_fn: GetChannelFn | None,
) -> dict[str, str] | None:
    """Download a single image attachment and cache it as a local file.

    Returns ``{"data_url": "file:///path/to/cached/image.jpg", "mime_type": "image/jpeg"}``
    or None on failure.  The ``data_url`` key name matches the expected
    schema in ``build_channel_inbound_query``; the harness MediaResolverProcessor
    detects non-base64 URLs and lazily resolves them.
    """
    raw_bytes = await _download_image_bytes(att, msg, get_channel_fn)
    if raw_bytes is None:
        return None

    compressed = _compress_image(raw_bytes)
    if compressed is not None and len(compressed) < len(raw_bytes):
        raw_bytes = compressed

    if len(raw_bytes) > MAX_IMAGE_BYTES:
        logger.warning("Image still too large after compression (%d bytes), skipping", len(raw_bytes))
        return None

    mime = _sniff_mime(raw_bytes) or att.mime_type or "image/jpeg"
    if not mime.startswith("image/"):
        mime = "image/jpeg"

    cached_path = _save_to_cache(raw_bytes, mime, msg)
    if cached_path is None:
        b64 = base64.b64encode(raw_bytes).decode("ascii")
        return {"data_url": f"data:{mime};base64,{b64}", "mime_type": mime}

    return {"data_url": f"file://{cached_path}", "mime_type": mime}


def _save_to_cache(raw_bytes: bytes, mime: str, msg: InboundMessage) -> str | None:
    """Save image bytes to a local cache directory and return the absolute path.

    Cache location: ``{DATA_DIR}/cache/channel_images/``
    Files are named with a content hash to enable deduplication.
    """
    try:
        from app.config.settings import settings as _settings

        cache_dir = Path(_settings.data_dir) / "cache" / "channel_images"
    except Exception:
        cache_dir = Path.home() / ".myrm" / "cache" / "channel_images"

    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        content_hash = hashlib.sha256(raw_bytes).hexdigest()[:16]
        ext = mime.split("/")[-1].replace("jpeg", "jpg")
        filename = f"{content_hash}.{ext}"
        file_path = cache_dir / filename

        if not file_path.exists():
            file_path.write_bytes(raw_bytes)
            logger.debug("Cached channel image: %s (%d bytes)", file_path, len(raw_bytes))

        return str(file_path)
    except Exception as exc:
        logger.warning("Failed to cache channel image: %s", exc)
        return None


async def _download_image_bytes(
    att: MediaAttachment,
    msg: InboundMessage,
    get_channel_fn: GetChannelFn | None,
) -> bytes | None:
    """Download image bytes from URL, path, or channel-specific file_id."""
    photo_file_id = msg.metadata.get("photo_file_id")
    if photo_file_id and callable(get_channel_fn):
        result = await _download_via_channel_api(str(photo_file_id), msg.channel, get_channel_fn)
        if result is not None:
            return result

    if att.url:
        return await _download_via_http(att.url)

    if att.path:
        return _read_local_file(att.path)

    return None


async def _download_via_channel_api(
    file_id: str,
    channel: str,
    get_channel_fn: GetChannelFn | None,
) -> bytes | None:
    """Download image via channel-specific API (e.g., Telegram getFile + downloadFile)."""
    if get_channel_fn is None:
        return None

    ch = get_channel_fn(channel)
    if ch is None or not hasattr(ch, "_client"):
        return None

    client = ch._client  # type: ignore[attr-defined]
    if not (hasattr(client, "get_file") and hasattr(client, "download_file")):
        return None

    try:
        file_info = await client.get_file(file_id)
        file_path = str(file_info.get("file_path", ""))
        if not file_path:
            return None
        return await client.download_file(file_path, timeout=DOWNLOAD_TIMEOUT)  # type: ignore[return-value]
    except Exception as exc:
        logger.warning("Image download via channel API failed: %s", exc)
        return None


async def _download_via_http(url: str) -> bytes | None:
    """Download image from a remote URL via HTTP."""
    try:
        from myrm_agent_harness.core.security.http.secure_fetch import secure_get

        response = await secure_get(url, timeout=DOWNLOAD_TIMEOUT)
        response.raise_for_status()
        data = response.content
        if len(data) > MAX_IMAGE_BYTES * 2:
            logger.warning("Image too large from URL (%d bytes), skipping", len(data))
            return None
        return data
    except Exception as exc:
        logger.warning("Image HTTP download failed for %s: %s", url[:120], exc)
        return None


def _read_local_file(path: str) -> bytes | None:
    """Read image from a local file path."""
    try:
        p = Path(path)
        if not p.is_file():
            return None
        data = p.read_bytes()
        if len(data) > MAX_IMAGE_BYTES * 2:
            logger.warning("Local image too large (%d bytes), skipping", len(data))
            return None
        return data
    except Exception as exc:
        logger.warning("Local image read failed for %s: %s", path, exc)
        return None


def _compress_image(raw_bytes: bytes) -> bytes | None:
    """Compress image bytes using ImageCompressor, returning JPEG bytes."""
    try:
        from myrm_agent_harness.utils.media.image_compressor import image_compressor

        result = image_compressor.compress(
            io.BytesIO(raw_bytes),
            quality=COMPRESS_QUALITY,
            max_dimension=MAX_DIMENSION_PX,
        )
        return result
    except Exception as exc:
        logger.warning("Image compression failed: %s", exc)
        return None


def _sniff_mime(data: bytes) -> str | None:
    """Detect image MIME type from magic bytes.

    Delegates to the centralized ``detect_image_mime`` utility.
    Returns ``None`` when detection falls back to the default so the
    caller can prefer the platform-declared MIME in that case.
    """
    from myrm_agent_harness.utils.mime_types import detect_image_mime

    detected = detect_image_mime(data, fallback="")
    return detected or None
