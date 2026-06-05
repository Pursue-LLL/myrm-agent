"""Matrix media upload and encrypted attachment helpers.

[INPUT]
- mautrix.client::Client (POS: mautrix Matrix client for upload/send)
- mautrix.crypto.attachments (POS: Attachment encryption for E2EE rooms)

[OUTPUT]
- send_media: Upload and send a media attachment to a Matrix room
- send_media_event: Send a media event with pre-uploaded mxc:// URL

[POS]
Media handling for MatrixChannel. Uploads files, encrypts attachments in E2EE
rooms, and sends m.image/m.audio/m.video/m.file events. Handles mxc:// URL
pass-through for already-uploaded media.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from app.channels.types import (
    MediaAttachment,
    MediaType,
)

logger = logging.getLogger(__name__)

_SEND_TIMEOUT = 30.0


async def send_media(
    client: object,
    room_id: str,
    att: MediaAttachment,
    encryption: bool,
) -> str | None:
    """Upload and send a media attachment. Returns event_id or None."""
    if not att.url and not att.path:
        return None
    if not client:
        return None

    from mautrix.types import RoomID

    data: bytes | None = None
    filename = att.filename or "file"
    content_type = att.mime_type or "application/octet-stream"

    if att.path:
        p = Path(att.path)
        if not p.exists():
            return None
        data = p.read_bytes()
    elif att.url:
        if att.url.startswith("mxc://"):
            return await send_media_event(
                client,
                room_id,
                att.url,
                filename,
                content_type,
                att.media_type,
            )
        return None

    if data is None:
        return None

    upload_data, encrypted_file = await _maybe_encrypt_attachment(
        client,
        RoomID(room_id),
        data,
        encryption,
    )

    try:
        mxc_url = await client.upload_media(  # type: ignore[union-attr]
            upload_data,
            mime_type=content_type,
            filename=filename,
            size=len(upload_data),
        )
    except Exception as exc:
        logger.error("Matrix: upload failed: %s", exc)
        return None

    return await send_media_event(
        client,
        room_id,
        str(mxc_url),
        filename,
        content_type,
        att.media_type,
        encrypted_file=encrypted_file,
        file_size=len(data),
    )


async def _maybe_encrypt_attachment(
    client: object,
    room_id: object,
    data: bytes,
    encryption: bool,
) -> tuple[bytes, object | None]:
    """Encrypt attachment data if E2EE is enabled and the room is encrypted."""
    if not encryption or not client or not getattr(client, "crypto", None):
        return data, None

    state_store = getattr(client, "state_store", None)
    if not state_store:
        return data, None

    try:
        room_encrypted = bool(await state_store.is_encrypted(room_id))
    except Exception:
        return data, None

    if not room_encrypted:
        return data, None

    try:
        from mautrix.crypto.attachments import encrypt_attachment

        encrypted_data, encrypted_file = encrypt_attachment(data)
        return encrypted_data, encrypted_file
    except Exception as exc:
        logger.error("Matrix: attachment encryption failed: %s", exc)
        return data, None


async def send_media_event(
    client: object,
    room_id: str,
    mxc_url: str,
    filename: str,
    content_type: str,
    media_type: MediaType,
    *,
    encrypted_file: object | None = None,
    file_size: int = 0,
) -> str | None:
    """Send a media event (m.image/m.audio/m.video/m.file) to a room."""
    if not client:
        return None

    from mautrix.types import EventType, RoomID

    type_map = {
        MediaType.IMAGE: "m.image",
        MediaType.AUDIO: "m.audio",
        MediaType.VIDEO: "m.video",
    }
    msg_type = type_map.get(media_type, "m.file")

    payload: dict[str, object] = {
        "msgtype": msg_type,
        "body": filename,
        "info": {"mimetype": content_type, "size": file_size},
    }

    if encrypted_file is not None:
        file_payload = encrypted_file.serialize()  # type: ignore[union-attr]
        file_payload["url"] = mxc_url
        payload["file"] = file_payload
    else:
        payload["url"] = mxc_url

    try:
        event_id = await asyncio.wait_for(
            client.send_message_event(  # type: ignore[union-attr]
                RoomID(room_id),
                EventType.ROOM_MESSAGE,
                payload,
            ),
            timeout=_SEND_TIMEOUT,
        )
        return str(event_id) if event_id else None
    except Exception as exc:
        logger.debug("Matrix media send failed: %s", exc)
        return None
