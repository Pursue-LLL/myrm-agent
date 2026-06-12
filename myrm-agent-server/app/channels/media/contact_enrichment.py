"""Contact (vCard) attachment enrichment for channel inbound messages.

Downloads vCard attachments, parses structured contact fields, and stores
them in message metadata for ``build_channel_inbound_query``.

[INPUT]
- channels.types::InboundMessage, MediaType, MediaAttachment
- channels.media.downloader::MediaDownloader (POS: SSRF-safe media download)

[OUTPUT]
- has_contact_attachment(): detect any CONTACT media attachment
- enrich_contact_inbound(): populate ``metadata["contact_cards"]``

[POS]
Channel router enrichment step (parallel to document/image enrichment).
"""

from __future__ import annotations

import dataclasses
import logging
import re
from typing import TYPE_CHECKING

from app.channels.types import InboundMessage, MediaType

if TYPE_CHECKING:
    from app.channels.types import MediaAttachment

logger = logging.getLogger(__name__)

MAX_CONTACTS_PER_MESSAGE = 5
MAX_VCARD_BYTES = 64 * 1024
DOWNLOAD_TIMEOUT = 10.0


def has_contact_attachment(msg: InboundMessage) -> bool:
    """True when the message has at least one contact-class attachment."""
    return any(att.media_type == MediaType.CONTACT for att in msg.media)


def _parse_vcard(text: str) -> dict[str, str | list[str]]:
    """Parse a vCard text into structured fields.

    Handles vCard 2.1/3.0/4.0 with BOM removal and line ending normalization.
    Returns a dict with keys: name, phones, emails, org, title, note, address, url, birthday.
    """
    cleaned = text.lstrip("\ufeff")
    cleaned = re.sub(r"\r\n[ \t]", "", cleaned)
    cleaned = re.sub(r"\r\n|\r", "\n", cleaned)

    name = ""
    phones: list[str] = []
    emails: list[str] = []
    org = ""
    title = ""
    note = ""
    address = ""
    url = ""
    birthday = ""

    for raw_line in cleaned.split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        colon_idx = line.find(":")
        if colon_idx == -1:
            continue

        key_part = line[:colon_idx].upper()
        value = line[colon_idx + 1:].strip()
        if not value:
            continue

        value = value.replace("\\n", " ").replace("\\,", ",").replace("\\;", ";")

        base_key = key_part.split(";")[0].split(".")[-1]

        if base_key == "FN" and not name:
            name = value
        elif base_key == "N" and not name:
            parts = [p.strip() for p in value.split(";") if p.strip()]
            name = " ".join(reversed(parts)) if parts else ""
        elif base_key == "TEL":
            phone = value.removeprefix("tel:").strip()
            if phone:
                phones.append(phone)
        elif base_key == "EMAIL":
            if value:
                emails.append(value)
        elif base_key == "ORG" and not org:
            org = value.replace(";", ", ").strip(", ")
        elif base_key == "TITLE" and not title:
            title = value
        elif base_key == "NOTE" and not note:
            note = value
        elif base_key == "ADR" and not address:
            parts = [p.strip() for p in value.split(";") if p.strip()]
            address = ", ".join(parts)
        elif base_key == "URL" and not url:
            url = value
        elif base_key == "BDAY" and not birthday:
            birthday = value

    result: dict[str, str | list[str]] = {}
    if name:
        result["name"] = name
    if phones:
        result["phones"] = phones
    if emails:
        result["emails"] = emails
    if org:
        result["org"] = org
    if title:
        result["title"] = title
    if note:
        result["note"] = note
    if address:
        result["address"] = address
    if url:
        result["url"] = url
    if birthday:
        result["birthday"] = birthday
    return result


def format_contact_text(card: dict[str, str | list[str]]) -> str:
    """Format a parsed contact card as a concise LLM-readable text block."""
    parts: list[str] = []
    name = card.get("name", "")
    if name:
        parts.append(f"Name: {name}")
    phones = card.get("phones")
    if isinstance(phones, list) and phones:
        parts.append(f"Phone: {', '.join(phones)}")
    emails_val = card.get("emails")
    if isinstance(emails_val, list) and emails_val:
        parts.append(f"Email: {', '.join(emails_val)}")
    org = card.get("org", "")
    if org:
        parts.append(f"Org: {org}")
    title_val = card.get("title", "")
    if title_val:
        parts.append(f"Title: {title_val}")
    note_val = card.get("note", "")
    if note_val:
        parts.append(f"Note: {note_val}")
    addr_val = card.get("address", "")
    if addr_val:
        parts.append(f"Address: {addr_val}")
    url_val = card.get("url", "")
    if url_val:
        parts.append(f"URL: {url_val}")
    bday_val = card.get("birthday", "")
    if bday_val:
        parts.append(f"Birthday: {bday_val}")
    return " | ".join(parts) if parts else "<contact>"


async def enrich_contact_inbound(msg: InboundMessage) -> InboundMessage:
    """Enrich inbound message with structured contact card data."""
    contact_attachments = [a for a in msg.media if a.media_type == MediaType.CONTACT]
    if not contact_attachments:
        return msg

    selected = contact_attachments[:MAX_CONTACTS_PER_MESSAGE]
    cards: list[dict[str, str | list[str]]] = []

    for att in selected:
        vcard_text = await _download_vcard(att)
        if not vcard_text:
            continue
        parsed = _parse_vcard(vcard_text)
        if parsed:
            cards.append(parsed)

    if not cards:
        return msg

    metadata = dict(msg.metadata) if isinstance(msg.metadata, dict) else {}
    metadata["contact_cards"] = cards
    return dataclasses.replace(msg, metadata=metadata)


async def _download_vcard(att: MediaAttachment) -> str | None:
    """Download or read vCard attachment content as text."""
    from pathlib import Path

    from app.channels.media import MediaDownloadConfig, MediaDownloader

    if att.url:
        config = MediaDownloadConfig(
            max_size_bytes=MAX_VCARD_BYTES,
            timeout_seconds=DOWNLOAD_TIMEOUT,
            allowed_content_types=None,
            enable_retry=False,
        )
        async with MediaDownloader(enable_default_cache=False) as downloader:
            result = await downloader.download(att.url, config=config)
            if result.success and result.data:
                try:
                    return result.data.decode("utf-8", errors="replace")
                except Exception:
                    logger.warning("Failed to decode vCard from %s", att.url)
                    return None

    if att.path:
        path = Path(att.path)
        if path.is_file() and path.stat().st_size <= MAX_VCARD_BYTES:
            try:
                return path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                logger.warning("Failed to read vCard file: %s", att.path)

    return None
