"""Email outbound: attachment loading and MIME message assembly.

[INPUT]
- channels.core.exceptions::ChannelSendError (POS: delivery failure)
- channels.media::MediaDownloadConfig, MediaDownloader (POS: SSRF-validated URL download)
- channels.types::MediaAttachment (POS: outbound attachment value type)

[OUTPUT]
- LoadedAttachment: attachment bytes with the name and MIME type they are mailed under
- load_attachments(): read local files / download URLs, returning what could not be loaded separately
- build_message(): HTML body plus attachments as one MIME message

[POS]
Outbound half of EmailChannel. The host owns the SMTP transport; this module turns an OutboundMessage's media
into MIME parts so an email carries the files the agent produced instead of silently dropping them.
"""

from __future__ import annotations

import asyncio
import email.encoders
import email.mime.base
import email.mime.multipart
import email.mime.text
import email.utils
import logging
import mimetypes
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path, PurePath
from urllib.parse import urlparse

from app.channels.core.exceptions import ChannelSendError
from app.channels.types import MediaAttachment

logger = logging.getLogger(__name__)

# SMTP servers commonly refuse messages above ~25 MB and base64 inflates attachments by 4/3.
MAX_ATTACHMENT_BYTES = 18 * 1024 * 1024
_DOWNLOAD_TIMEOUT = 60.0
_FALLBACK_MIME = "application/octet-stream"


@dataclass(frozen=True, slots=True)
class LoadedAttachment:
    filename: str
    mime_type: str
    data: bytes


def _filename(attachment: MediaAttachment) -> str:
    if attachment.filename:
        return attachment.filename
    source = attachment.path or urlparse(attachment.url or "").path
    return PurePath(source).name or attachment.media_type.value


def _mime_type(attachment: MediaAttachment, filename: str, content_type: str | None) -> str:
    return attachment.mime_type or content_type or mimetypes.guess_type(filename)[0] or _FALLBACK_MIME


def _read_local(path: Path) -> bytes:
    size = path.stat().st_size
    if size > MAX_ATTACHMENT_BYTES:
        raise ChannelSendError(f"Email attachment {path.name} is too large ({size} bytes)", retriable=False)
    return path.read_bytes()


async def _load_attachment(attachment: MediaAttachment) -> LoadedAttachment:
    filename = _filename(attachment)
    if attachment.path:
        try:
            data = await asyncio.to_thread(_read_local, Path(attachment.path))
        except OSError as exc:
            raise ChannelSendError(f"Email attachment {filename} is unreadable: {exc}", retriable=False) from exc
        return LoadedAttachment(filename, _mime_type(attachment, filename, None), data)

    if not attachment.url:
        raise ChannelSendError(f"Email attachment {filename} has neither path nor url", retriable=False)

    from app.channels.media import MediaDownloadConfig, MediaDownloader

    config = MediaDownloadConfig(timeout_seconds=_DOWNLOAD_TIMEOUT, max_size_bytes=MAX_ATTACHMENT_BYTES)
    async with MediaDownloader(enable_default_cache=False) as downloader:
        result = await downloader.download(attachment.url, config=config)
    if not result.success or not result.data:
        raise ChannelSendError(f"Email attachment {filename} could not be downloaded")
    return LoadedAttachment(filename, _mime_type(attachment, filename, result.content_type), result.data)


async def load_attachments(media: Sequence[MediaAttachment]) -> tuple[list[LoadedAttachment], list[str]]:
    """Load every attachment; return ``(loaded, display names of the ones that could not be loaded)``."""
    loaded: list[LoadedAttachment] = []
    failed: list[str] = []
    for attachment in media:
        try:
            loaded.append(await _load_attachment(attachment))
        except ChannelSendError as exc:
            logger.warning("Email: attachment %s not loaded: %s", attachment.display_name, exc)
            failed.append(attachment.display_name)
    return loaded, failed


def build_message(
    from_address: str,
    to_address: str,
    subject: str,
    body_html: str,
    in_reply_to: str | None,
    attachments: Sequence[LoadedAttachment],
) -> tuple[email.mime.multipart.MIMEMultipart, str]:
    """Assemble the MIME message and return it with its Message-ID."""
    body = email.mime.multipart.MIMEMultipart("alternative")
    body.attach(email.mime.text.MIMEText(body_html, "html"))

    message = email.mime.multipart.MIMEMultipart("mixed") if attachments else body
    if attachments:
        message.attach(body)
        for item in attachments:
            maintype, _, subtype = item.mime_type.partition("/")
            part = email.mime.base.MIMEBase(maintype, subtype or "octet-stream")
            part.set_payload(item.data)
            email.encoders.encode_base64(part)
            part.add_header("Content-Disposition", "attachment", filename=item.filename)
            message.attach(part)

    message["From"] = from_address
    message["To"] = to_address
    message["Subject"] = subject
    message_id = email.utils.make_msgid()
    message["Message-ID"] = message_id
    if in_reply_to:
        message["In-Reply-To"] = in_reply_to
        message["References"] = in_reply_to
    return message, message_id
