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
- app.config.settings::settings (POS: 统一配置中心，提供状态目录 settings.database.state_dir)
- myrm_agent_harness.core.security.http.secure_fetch::secure_get / ContentTooLargeError (POS: SSRF-protected image download with size cap)

[OUTPUT]
- has_image_attachment(): check for image media
- enrich_image_inbound(): download, compress, cache images as files into metadata
- channel_image_cache_dir(): where the cached images live
- sweep_channel_image_cache(): remove cached images unused for the retention period
- sweep_channel_image_cache_at_startup(): that sweep as a maintenance-daemon task, submitted when the server starts

[POS]
Image attachment data preparation for channel router.
Stores file path references in ``msg.metadata["image_data_list"]`` for
downstream multimodal query construction in the business layer.
Owns the lifetime of the cache it fills: the daily context cleanup job and the server's startup call the sweep.
"""

from __future__ import annotations

import asyncio
import base64
import dataclasses
import hashlib
import logging
import os
import time
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
# Long enough that a conversation resumed after weeks still shows its pictures, short enough to bound the directory.
CHANNEL_IMAGE_RETENTION_DAYS = 30
_SECONDS_PER_DAY = 86400


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
        if isinstance(result, BaseException):
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

    cached_path = _save_to_cache(raw_bytes, mime)
    if cached_path is None:
        b64 = base64.b64encode(raw_bytes).decode("ascii")
        return {"data_url": f"data:{mime};base64,{b64}", "mime_type": mime}

    return {"data_url": f"file://{cached_path}", "mime_type": mime}


def channel_image_cache_dir() -> Path:
    """``{state_dir}/cache/channel_images/``: the images of received messages, one file per distinct image."""
    from app.config.settings import settings

    return Path(settings.database.state_dir) / "cache" / "channel_images"


def _save_to_cache(raw_bytes: bytes, mime: str) -> str | None:
    """Save image bytes to the channel image cache and return the absolute path, or None when it cannot be cached.

    Files are named with a content hash to enable deduplication. An image that is already cached is not written
    again, but its age restarts: the retention sweep counts from the last time an image was received.
    """
    try:
        cache_dir = channel_image_cache_dir()
        cache_dir.mkdir(parents=True, exist_ok=True)
        content_hash = hashlib.sha256(raw_bytes).hexdigest()[:16]
        ext = mime.split("/")[-1].replace("jpeg", "jpg")
        filename = f"{content_hash}.{ext}"
        file_path = cache_dir / filename

        try:
            # utime, not touch: a file removed in between must not come back as an empty image.
            os.utime(file_path)
        except FileNotFoundError:
            file_path.write_bytes(raw_bytes)
            logger.debug("Cached channel image: %s (%d bytes)", file_path, len(raw_bytes))

        return str(file_path)
    except Exception as exc:
        logger.warning("Failed to cache channel image: %s", exc)
        return None


def sweep_channel_image_cache() -> int:
    """Remove cached images not received for ``CHANNEL_IMAGE_RETENTION_DAYS``; return how many were removed.

    History that still cites a removed image loses that picture: the harness resolver skips a missing file.
    Files that cannot be removed (read-only volume, permissions) are left and reported in one warning, so the others
    are still swept and a whole unwritable directory does not log once per file.
    """
    try:
        entries = list(channel_image_cache_dir().iterdir())
    except FileNotFoundError:
        return 0

    cutoff = time.time() - CHANNEL_IMAGE_RETENTION_DAYS * _SECONDS_PER_DAY
    removed = 0
    failures: list[str] = []
    for entry in entries:
        try:
            if entry.is_file() and entry.stat().st_mtime < cutoff:
                entry.unlink()
                removed += 1
        except FileNotFoundError:
            continue  # removed by someone else in between: nothing left to do
        except OSError as exc:
            failures.append(f"{entry.name}: {exc}")
    if failures:
        logger.warning("Failed to remove %d expired channel images, first: %s", len(failures), failures[0])
    return removed


async def sweep_channel_image_cache_at_startup() -> None:
    """Sweep once when the server starts, as a unit of work for the maintenance daemon.

    The daily cleanup job runs at 03:00 only while the server is up, so a machine that is off at that hour would never
    sweep and its cache would only grow. Listing and removing files blocks, so it runs in a worker thread.
    """
    removed = await asyncio.to_thread(sweep_channel_image_cache)
    if removed > 0:
        logger.info("Startup: removed %d expired channel images", removed)


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

    client = getattr(get_channel_fn(channel), "_client", None)
    if client is None or not (hasattr(client, "get_file") and hasattr(client, "download_file")):
        return None

    try:
        file_info = await client.get_file(file_id)
        file_path = str(file_info.get("file_path", ""))
        if not file_path:
            return None
        data = await client.download_file(file_path, timeout=DOWNLOAD_TIMEOUT)
        return data if isinstance(data, bytes) else None
    except Exception as exc:
        logger.warning("Image download via channel API failed: %s", exc)
        return None


async def _download_via_http(url: str) -> bytes | None:
    """Download image from a remote URL via HTTP."""
    try:
        from myrm_agent_harness.core.security.http.secure_fetch import (
            ContentTooLargeError,
            secure_get,
        )

        response = await secure_get(
            url,
            timeout=DOWNLOAD_TIMEOUT,
            max_content_length=MAX_IMAGE_BYTES * 2,
        )
        response.raise_for_status()
        return response.content
    except ContentTooLargeError:
        logger.warning("Image too large from URL (cap %d), skipping", MAX_IMAGE_BYTES * 2)
        return None
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
    """Responsive image compression, preserving animated GIFs and returning None on failure."""
    try:
        from myrm_agent_harness.utils.media.image_compressor import image_compressor

        # Responsive compression with animation protection: animated GIFs and images
        # already under the 1568px / byte threshold pass through untouched.
        result = image_compressor.compress_if_needed(
            raw_bytes,
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
