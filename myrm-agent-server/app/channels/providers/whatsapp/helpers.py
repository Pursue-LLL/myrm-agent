"""WhatsApp channel — pure helper functions and constants.

Stateless utilities shared by the channel and bridge modules.

[INPUT]

[OUTPUT]
- Constants: _MAX_TEXT_LENGTH, _BRIDGE_DIR, _BRIDGE_SCRIPT, _PROCESS_STOP_TIMEOUT
- Functions: _default_auth_dir, _prefer_pn_jid, _strip_device_suffix, _normalize_jid,
             check_mentioned, is_self_chat, parse_message_key

[POS]
WhatsApp JID normalization, mention detection, self-chat detection, and path constants.
Shared by channel.py and bridge.py.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_MAX_TEXT_LENGTH = 4096
_BRIDGE_DIR = Path(__file__).resolve().parent / "bridge"
_BRIDGE_SCRIPT = _BRIDGE_DIR / "whatsapp-bridge.js"
_PROCESS_STOP_TIMEOUT = 10


def _default_auth_dir() -> Path:
    """MYRM_DATA_DIR/whatsapp_auth — consistent with other user data."""
    import os

    data_dir = os.environ.get("MYRM_DATA_DIR", str(Path.home() / ".myrm"))
    return Path(data_dir) / "whatsapp_auth"


def _prefer_pn_jid(primary: str, alt: object) -> str:
    """Return the @s.whatsapp.net JID, preferring it over @lid for pairing compatibility.

    WhatsApp LID (Linked ID) uses a different identifier than the phone
    number. Pairing store entries use @s.whatsapp.net, so we prefer that
    format. Baileys provides 'remoteJidAlt' / 'participantAlt' as the
    alternate JID when the primary is in the other format.
    """
    alt_str = str(alt) if isinstance(alt, str) and alt else ""
    if primary.endswith("@s.whatsapp.net"):
        return _strip_device_suffix(primary)
    if alt_str.endswith("@s.whatsapp.net"):
        return _strip_device_suffix(alt_str)
    return _strip_device_suffix(primary)


def _strip_device_suffix(jid: str) -> str:
    """Remove Baileys device suffix: '8615546316576:5@s.whatsapp.net' → '8615546316576@s.whatsapp.net'."""
    if ":" in jid and "@" in jid:
        local, domain = jid.split("@", 1)
        local = local.split(":")[0]
        return f"{local}@{domain}"
    return jid


def _normalize_jid(recipient_id: str) -> str:
    """Ensure recipient_id is a valid WhatsApp JID."""
    if "@" in recipient_id:
        return _strip_device_suffix(recipient_id)
    digits = "".join(c for c in recipient_id if c.isdigit())
    return f"{digits}@s.whatsapp.net"


def check_mentioned(
    event: dict[str, object],
    self_jid: str | None,
    lid_to_pn: dict[str, str] | None = None,
) -> bool:
    """Check if the bot was mentioned or replied-to in a group message.

    Args:
        event: Bridge message event dict.
        self_jid: The bot's own JID (e.g. '8615546316576@s.whatsapp.net').
        lid_to_pn: LID-to-phone-number mapping for resolving @lid JIDs.
    """
    if event.get("replyToBot") is True:
        logger.debug("WhatsApp mention: detected via replyToBot=True")
        return True
    if not self_jid:
        logger.warning("WhatsApp mention: self_jid is None, cannot detect mentions")
        return False
    mentioned_jids = event.get("mentionedJids")
    if not isinstance(mentioned_jids, list):
        logger.debug("WhatsApp mention: mentionedJids not a list (got %s)", type(mentioned_jids))
        return False

    self_number = self_jid.split("@")[0].split(":")[0]
    logger.debug(
        "WhatsApp mention check: self_number=%s, mentionedJids=%s",
        self_number,
        mentioned_jids,
    )

    for jid in mentioned_jids:
        jid_str = str(jid)
        jid_number = jid_str.split("@")[0].split(":")[0]
        if jid_number == self_number:
            logger.debug("WhatsApp mention: MATCHED via JID %s", jid)
            return True
        if jid_str.endswith("@lid") and lid_to_pn:
            pn = lid_to_pn.get(jid_str)
            if pn and _strip_device_suffix(pn).split("@")[0] == self_number:
                logger.debug("WhatsApp mention: MATCHED via LID→PN %s→%s", jid, pn)
                return True

    logger.debug("WhatsApp mention: NOT matched (bot not in mentionedJids)")
    return False


def is_self_chat(remote_jid: str, self_jid: str | None, lid_to_pn: dict[str, str]) -> bool:
    """Check if remoteJid corresponds to self-chat (same phone number or LID).

    For LID-format JIDs, resolves to phone number via lid_to_pn cache
    before comparing. Returns False for unresolvable LIDs to avoid
    misrouting outbound messages as self-chat.
    """
    if not self_jid:
        return False
    self_number = _strip_device_suffix(self_jid).split("@")[0]
    remote_number = remote_jid.split("@")[0].split(":")[0]
    if self_number == remote_number:
        return True
    if remote_jid.endswith("@lid"):
        pn = lid_to_pn.get(remote_jid)
        if pn:
            return _strip_device_suffix(pn).split("@")[0] == self_number
    return False


def parse_message_key(message_id: str) -> dict[str, object] | None:
    """Parse a JSON-serialized Baileys message key, returning None on failure."""
    try:
        key = json.loads(message_id)
        return key if isinstance(key, dict) else None
    except (json.JSONDecodeError, TypeError):
        logger.warning("WhatsApp: invalid message key: %s", message_id[:50])
        return None
