"""Outbound attachment guard: credential and key files never leave the machine through an IM channel.

[INPUT]
- myrm_agent_harness.core.security.path::is_sensitive_file (POS: protected-path policy, credential and secret file names)
- channels.i18n::channel_t, get_locale_from_metadata (POS: localized withheld notice)
- channels.types::MediaAttachment, OutboundMessage (POS: outbound payload)

[OUTPUT]
- withhold_sensitive_attachments: drop key/credential attachments and name them in the message text

[POS]
Last hop before the provider for attachments whose producers (deliverable scanner, tool artifacts, agent
replies) never look at what a file is, in a chat that has no confirmation step. A seatbelt, not a classifier:
it matches names, so a secret renamed to something harmless still passes.
"""

from __future__ import annotations

import dataclasses
import logging
import os

from myrm_agent_harness.core.security.path import is_sensitive_file

from app.channels.i18n import channel_t, get_locale_from_metadata
from app.channels.types import MediaAttachment, OutboundMessage

logger = logging.getLogger(__name__)

# Keynote documents use the private-key extension but are ZIP archives; PEM/DER keys never are.
_KEYNOTE_EXTENSION = ".key"
_ZIP_SIGNATURE = b"PK\x03\x04"


def withhold_sensitive_attachments(msg: OutboundMessage) -> OutboundMessage:
    """Remove local attachments that look like keys or credentials and name them in the message text.

    Returns ``msg`` itself when nothing is withheld.
    """
    kept: list[MediaAttachment] = []
    withheld: list[MediaAttachment] = []
    for attachment in msg.media:
        (withheld if _is_sensitive(attachment) else kept).append(attachment)
    if not withheld:
        return msg

    locale = get_locale_from_metadata(msg.metadata)
    notes = "\n".join(str(channel_t(locale, "attachment_withheld_note", name=m.display_name)) for m in withheld)
    logger.warning(
        "Withheld %d sensitive attachment(s) from an outbound message on channel '%s': %s",
        len(withheld),
        msg.channel,
        ", ".join(m.display_name for m in withheld),
    )
    return dataclasses.replace(msg, media=tuple(kept), content=f"{msg.content}\n\n{notes}" if msg.content else notes)


def _is_sensitive(attachment: MediaAttachment) -> bool:
    """Whether a local attachment is key material; ephemeral temp files (made by the system) and URLs are not inspected."""
    if attachment.ephemeral or not attachment.path:
        return False
    # The link target counts too, so a harmless-looking symlink cannot carry a credential out.
    resolved = os.path.realpath(attachment.path)
    if not (is_sensitive_file(attachment.path) or is_sensitive_file(resolved)):
        return False
    return not (os.path.splitext(resolved)[1].lower() == _KEYNOTE_EXTENSION and _is_zip_archive(resolved))


def _is_zip_archive(path: str) -> bool:
    try:
        with open(path, "rb") as file:
            return file.read(len(_ZIP_SIGNATURE)) == _ZIP_SIGNATURE
    except OSError:
        return False
