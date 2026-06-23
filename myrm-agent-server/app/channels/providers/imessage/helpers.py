"""iMessage channel helper functions and constants.

[POS]
Stateless utilities shared across the iMessage channel module.
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import quote, urlparse

from app.channels.types import MediaType

SEND_TIMEOUT = 15.0
MEDIA_TIMEOUT = 30.0
MAX_TEXT_LENGTH = 10000

TAPBACK_MAP: dict[str, int] = {
    "\u2764\ufe0f": 2000,
    "\U0001f44d": 2001,
    "\U0001f44e": 2002,
    "\U0001f602": 2003,
    "\u2757": 2004,
    "\u203c\ufe0f": 2004,
    "\u2753": 2005,
    "\U0001f440": 2001,
}
TAPBACK_CODE_TO_EMOJI: dict[int, str] = {
    2000: "\u2764\ufe0f",
    2001: "\U0001f44d",
    2002: "\U0001f44e",
    2003: "\U0001f602",
    2004: "\u2757",
    2005: "\u2753",
}


def quote_guid(guid: str) -> str:
    """URL-encode a BlueBubbles chat GUID for use in path segments.

    Chat GUIDs contain `;` and `+` (e.g. `iMessage;-;+15551234567`)
    which must be percent-encoded when embedded in a URL path.
    """
    return quote(guid, safe="")


def mime_to_media_type(mime: str) -> MediaType:
    lower = mime.lower()
    if lower in ("text/vcard", "text/x-vcard", "text/directory", "application/vcard", "application/x-vcard"):
        return MediaType.CONTACT
    if lower.startswith("image/"):
        return MediaType.IMAGE
    if lower.startswith("audio/"):
        return MediaType.AUDIO
    if lower.startswith("video/"):
        return MediaType.VIDEO
    return MediaType.DOCUMENT


def filename_from_url(url: str) -> str:
    name = Path(urlparse(url).path).name
    return name or "download.bin"
