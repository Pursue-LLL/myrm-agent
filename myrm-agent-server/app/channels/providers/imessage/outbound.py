"""iMessage outbound requests to BlueBubbles: text, attachment upload and Tapback.

[INPUT]
- httpx::AsyncClient (POS: the channel's HTTP client, handed in per call so a replaced client is honoured)
- channels.core.exceptions::ChannelSendError (POS: delivery failure carrying the retry semantics)
- channels.media (POS: MediaDownloader fetches a URL attachment; imported on use)
- channels.providers.imessage.helpers (POS: channel name, timeouts, file name from a URL)

[OUTPUT]
- send_text / send_attachment: deliver one message or one file, returning the guid BlueBubbles reports
- post_tapback: send or remove a Tapback
- read_media / reported_guid: attachment bytes with their name and type; the guid of an accepted send

[POS]
The wire contract with BlueBubbles' ``/api/v1/message`` endpoints, kept apart from the channel so that what the
server sees can be read and tested without the channel's lifecycle. Every function raises ``ChannelSendError``
when BlueBubbles refuses the request or cannot be reached.
"""

from __future__ import annotations

import asyncio
import mimetypes
import uuid
from pathlib import Path

import httpx

from app.channels.core.exceptions import ChannelSendError
from app.channels.types import MediaAttachment

from .helpers import CHANNEL_NAME, MEDIA_TIMEOUT, SEND_TIMEOUT, filename_from_url


async def send_text(
    http: httpx.AsyncClient,
    api_url: str,
    password: str,
    chat_guid: str,
    text: str,
    *,
    quote: str | None = None,
) -> str | None:
    """Send a text message, quoting ``quote`` (a message guid) through the Private API when given."""
    payload: dict[str, object] = {"chatGuid": chat_guid, "tempGuid": f"temp-{uuid.uuid4()}", "message": text}
    if quote:
        payload["method"] = "private-api"
        payload["selectedMessageGuid"] = quote
        payload["partIndex"] = 0
    try:
        resp = await http.post(
            f"{api_url}/api/v1/message/text",
            params={"password": password},
            json=payload,
            timeout=SEND_TIMEOUT,
        )
    except Exception as exc:
        raise ChannelSendError(f"iMessage text send failed: {exc}", channel=CHANNEL_NAME) from exc
    if resp.status_code >= 400:
        raise ChannelSendError.from_http_status(CHANNEL_NAME, resp.status_code)
    return reported_guid(resp)


async def send_attachment(
    http: httpx.AsyncClient, api_url: str, password: str, chat_guid: str, att: MediaAttachment
) -> str | None:
    """Upload a media attachment as multipart; raises when it cannot be read or does not arrive."""
    data, filename, mime = await read_media(http, att)
    try:
        resp = await http.post(
            f"{api_url}/api/v1/message/attachment",
            params={"password": password},
            data={"chatGuid": chat_guid, "tempGuid": f"temp-{uuid.uuid4()}", "name": filename},
            files={"attachment": (filename, data, mime)},
            timeout=MEDIA_TIMEOUT,
        )
    except Exception as exc:
        raise ChannelSendError(f"iMessage attachment send failed: {exc}", channel=CHANNEL_NAME) from exc
    if resp.status_code >= 400:
        raise ChannelSendError.from_http_status(CHANNEL_NAME, resp.status_code)
    return reported_guid(resp)


async def post_tapback(
    http: httpx.AsyncClient, api_url: str, password: str, chat_guid: str, message_guid: str, reaction: str
) -> None:
    """Post a Tapback name (or its ``-`` removal) on a message; a refusal raises, a transport error propagates."""
    resp = await http.post(
        f"{api_url}/api/v1/message/react",
        params={"password": password},
        json={"chatGuid": chat_guid, "selectedMessageGuid": message_guid, "reaction": reaction},
        timeout=SEND_TIMEOUT,
    )
    if resp.status_code >= 400:
        raise ChannelSendError(
            f"iMessage reaction failed: HTTP {resp.status_code}", channel=CHANNEL_NAME, status_code=resp.status_code
        )


def reported_guid(resp: httpx.Response) -> str | None:
    """Guid BlueBubbles reports for an accepted send; an unreadable body leaves delivery unconfirmed."""
    try:
        data = resp.json().get("data")
    except ValueError:
        return None
    return (str(data.get("guid") or "") or None) if isinstance(data, dict) else None


async def read_media(http: httpx.AsyncClient, att: MediaAttachment) -> tuple[bytes, str, str]:
    """Read media bytes from the URL or the local path; raises ``ChannelSendError`` when neither yields data."""
    if att.url:
        from app.channels.media import (
            MAX_FORWARD_DOWNLOAD_BYTES,
            MediaDownloadConfig,
            MediaDownloader,
        )

        config = MediaDownloadConfig(timeout_seconds=MEDIA_TIMEOUT, max_size_bytes=MAX_FORWARD_DOWNLOAD_BYTES)
        downloader = MediaDownloader(http_client=http, enable_default_cache=True)
        result = await downloader.download(att.url, config=config)
        if result.success and result.data:
            name = att.filename or filename_from_url(att.url)
            mime = att.mime_type or result.content_type or "application/octet-stream"
            return result.data, name, mime

    if att.path:
        path = Path(att.path)
        if path.is_file():
            data = await asyncio.to_thread(path.read_bytes)
            mime = att.mime_type or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            return data, path.name, mime

    # A failed download may work next time; a missing local file never will.
    raise ChannelSendError(f"iMessage cannot read {att.display_name}", channel=CHANNEL_NAME, retriable=bool(att.url))
