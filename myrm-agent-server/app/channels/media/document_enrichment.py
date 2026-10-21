"""Document attachment enrichment for channel inbound messages.

Downloads PDF/Office attachments, optionally extracts text via
``app.services.files.content_extraction``, and stores blocks in message
metadata for ``build_channel_inbound_query``.

[INPUT]
- channels.types::InboundMessage, MediaType, MediaAttachment
- channels.media.downloader::MediaDownloader (POS: SSRF-safe media download)
- services.files.content_extraction (POS: PDF/Office text extraction)

[OUTPUT]
- has_document_attachment(): detect any DOCUMENT media attachment
- enrich_document_inbound(): populate ``metadata["document_text_blocks"]``

[POS]
Channel router enrichment step (parallel to image_enrichment).
"""

from __future__ import annotations

import dataclasses
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

MAX_DOCUMENTS_PER_MESSAGE = 4
MAX_DOCUMENT_BYTES = 20 * 1024 * 1024
DOWNLOAD_TIMEOUT = 30.0
MAX_DOCUMENT_TEXT_CHARS = 200_000

_PDF_EXTENSIONS = frozenset({".pdf"})
_OFFICE_EXTENSIONS = frozenset({".docx", ".xlsx", ".xls", ".pptx", ".ppt"})


def has_document_attachment(msg: InboundMessage) -> bool:
    """True when the message has at least one document-class attachment."""
    return any(att.media_type == MediaType.DOCUMENT for att in msg.media)


def _attachment_label(att: MediaAttachment) -> str:
    return att.filename or att.path or att.url or "attachment"


def _can_extract_text(att: MediaAttachment) -> bool:
    if att.media_type != MediaType.DOCUMENT:
        return False
    name = (att.filename or att.path or att.url or "").lower()
    if any(name.endswith(ext) for ext in _PDF_EXTENSIONS | _OFFICE_EXTENSIONS):
        return True
    mime = (att.mime_type or "").lower()
    if mime == "application/pdf":
        return True
    if mime in (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ):
        return True
    return False


async def enrich_document_inbound(
    msg: InboundMessage,
    get_channel_fn: GetChannelFn | None,
    *,
    extract_enabled: bool,
) -> InboundMessage:
    """Enrich inbound message with document text blocks or filename references."""
    doc_attachments = [a for a in msg.media if a.media_type == MediaType.DOCUMENT]
    if not doc_attachments:
        return msg

    selected = doc_attachments[:MAX_DOCUMENTS_PER_MESSAGE]
    blocks: list[dict[str, str]] = []

    for att in selected:
        label = _attachment_label(att)
        if not extract_enabled or not _can_extract_text(att):
            blocks.append(
                {
                    "filename": label,
                    "text": f"[Attachment: {label}]",
                }
            )
            continue

        raw = await _download_document_bytes(att, msg, get_channel_fn)
        if raw is None:
            blocks.append(
                {
                    "filename": label,
                    "text": f"[Attachment: {label}] (download failed)",
                }
            )
            continue

        if len(raw) > MAX_DOCUMENT_BYTES:
            logger.warning(
                "Document enrichment: file too large (%d bytes), skipping extract: %s",
                len(raw),
                label,
            )
            blocks.append(
                {
                    "filename": label,
                    "text": f"[Attachment: {label}] (file too large for extraction)",
                }
            )
            continue

        text = await _extract_text_from_bytes(raw, filename=label, mime_type=att.mime_type)
        if not text:
            blocks.append(
                {
                    "filename": label,
                    "text": f"[Attachment: {label}] (extraction produced no text)",
                }
            )
            continue

        if len(text) > MAX_DOCUMENT_TEXT_CHARS:
            preview = text[:MAX_DOCUMENT_TEXT_CHARS]
            blocks.append(
                {
                    "filename": label,
                    "text": (
                        f"## Attachment: {label}\n{preview}\n\n"
                        f"... [truncated at {MAX_DOCUMENT_TEXT_CHARS} chars — "
                        f"full document is {len(text)} chars]"
                    ),
                }
            )
        else:
            blocks.append(
                {
                    "filename": label,
                    "text": f"## Attachment: {label}\n{text}",
                }
            )

    if not blocks:
        return msg

    new_metadata = dict(msg.metadata)
    new_metadata["document_text_blocks"] = blocks
    logger.info(
        "Document enrichment: %d block(s) for %s/%s (extract=%s)",
        len(blocks),
        msg.channel,
        msg.sender_id,
        extract_enabled,
    )
    return dataclasses.replace(msg, metadata=new_metadata)


async def _extract_text_from_bytes(
    raw: bytes,
    *,
    filename: str,
    mime_type: str | None,
) -> str:
    from app.services.files.content_extraction import (
        extract_document_text_from_bytes,
        extract_pdf_text_from_bytes,
    )

    lower = filename.lower()
    mime = (mime_type or "").lower()
    if lower.endswith(".pdf") or mime == "application/pdf":
        return await extract_pdf_text_from_bytes(raw)
    return await extract_document_text_from_bytes(raw, filename=filename)


async def _download_document_bytes(
    att: MediaAttachment,
    msg: InboundMessage,
    get_channel_fn: GetChannelFn | None,
) -> bytes | None:
    if att.url:
        return await _download_via_media_downloader(att.url)
    if att.path:
        return _read_local_file(att.path)
    file_id = msg.metadata.get("document_file_id")
    if file_id and callable(get_channel_fn):
        return await _download_via_channel_api(str(file_id), msg.channel, get_channel_fn)
    return None


async def _download_via_media_downloader(url: str) -> bytes | None:
    from app.channels.media import MediaDownloadConfig, MediaDownloader

    config = MediaDownloadConfig(
        max_size_bytes=MAX_DOCUMENT_BYTES,
        timeout_seconds=DOWNLOAD_TIMEOUT,
        allowed_content_types=None,
        validate_ssrf=True,
    )
    try:
        async with MediaDownloader(enable_default_cache=True) as downloader:
            result = await downloader.download(url, config=config)
        if not result.success or not result.data:
            logger.warning(
                "Document download failed for %s: %s",
                url[:120],
                result.error,
            )
            return None
        return result.data
    except Exception as exc:
        logger.warning("Document download failed for %s: %s", url[:120], exc)
        return None


def _read_local_file(path: str) -> bytes | None:
    try:
        p = Path(path)
        if not p.is_file():
            return None
        data = p.read_bytes()
        if len(data) > MAX_DOCUMENT_BYTES * 2:
            logger.warning("Local document too large (%d bytes)", len(data))
            return None
        return data
    except Exception as exc:
        logger.warning("Local document read failed for %s: %s", path, exc)
        return None


async def _download_via_channel_api(
    file_id: str,
    channel: str,
    get_channel_fn: GetChannelFn | None,
) -> bytes | None:
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
        logger.warning("Document download via channel API failed: %s", exc)
        return None
