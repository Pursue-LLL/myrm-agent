"""MSTeams message parsing and formatting helpers.

Pure functions for HTML entity decoding, mention tag stripping,
quote context extraction, message key encoding, and Adaptive Card building.

[INPUT]
- channels.types.components::ActionButton, (POS: UI component type definitions Cross-channel interactive component abstractions  Support in)

[OUTPUT]
- decode_html_entities, strip_mention_tags, html_to_plain
- extract_quote_context
- encode_message_key, decode_message_key
- build_adaptive_card_activity

[POS]
Stateless helpers extracted from MSTeamsChannel to keep channel.py focused
on the Channel lifecycle and I/O.
"""

from __future__ import annotations

import json
import re

from app.channels.types.components import (
    ActionButton,
    ButtonStyle,
    ComponentRow,
    QuickReply,
)

_AT_TAG_RE = re.compile(r"<at[^>]*>.*?</at>", re.IGNORECASE)
_HTML_TAG_RE = re.compile(r"<[^>]*>")
_HTML_ENTITIES: dict[str, str] = {
    "&lt;": "<",
    "&gt;": ">",
    "&quot;": '"',
    "&#39;": "'",
    "&#x27;": "'",
    "&nbsp;": " ",
    "&amp;": "&",
}

EMOJI_TO_TEAMS_REACTION: dict[str, str] = {
    "\U0001f44d": "like",
    "\U0001f44e": "like",
    "\u2764\ufe0f": "heart",
    "\U0001faf6": "heart",
    "\U0001f602": "laugh",
    "\U0001f923": "laugh",
    "\U0001f62e": "surprised",
    "\U0001f632": "surprised",
    "\U0001f622": "sad",
    "\U0001f62d": "sad",
    "\U0001f620": "angry",
    "\U0001f621": "angry",
    "\U0001f440": "like",
    "\u2705": "like",
    "\U0001f914": "like",
}


def decode_html_entities(text: str) -> str:
    for entity, char in _HTML_ENTITIES.items():
        text = text.replace(entity, char)
    return text


def strip_mention_tags(text: str) -> str:
    """Remove Teams <at>...</at> mention wrappers, preserving surrounding text."""
    return _AT_TAG_RE.sub("", text).strip()


def html_to_plain(html: str) -> str:
    text = _HTML_TAG_RE.sub(" ", html)
    text = " ".join(text.split())
    return decode_html_entities(text).strip()


def extract_quote_context(
    attachments: list[dict[str, object]],
) -> dict[str, str] | None:
    """Extract quoted reply context from Teams HTML reply attachments."""
    for att in attachments:
        content = att.get("content", "")
        if not isinstance(content, str) or "http://schema.skype.com/Reply" not in content:
            continue
        sender_match = re.search(
            r'<strong[^>]*itemprop=["\']mri["\'][^>]*>(.*?)</strong>',
            content,
            re.IGNORECASE,
        )
        body_match = re.search(
            r'<p[^>]*itemprop=["\']copy["\'][^>]*>(.*?)</p>',
            content,
            re.IGNORECASE | re.DOTALL,
        )
        if body_match:
            return {
                "quote_sender": html_to_plain(sender_match.group(1)) if sender_match else "unknown",
                "quote_body": html_to_plain(body_match.group(1)),
            }
    return None


def encode_message_key(activity_id: str, service_url: str, conversation_id: str) -> str:
    return json.dumps(
        {"aid": activity_id, "surl": service_url, "cid": conversation_id},
        separators=(",", ":"),
    )


def decode_message_key(key: str) -> tuple[str, str, str] | None:
    """Returns (activity_id, service_url, conversation_id) or None."""
    try:
        d = json.loads(key)
        return str(d["aid"]), str(d["surl"]), str(d["cid"])
    except (json.JSONDecodeError, KeyError, TypeError):
        return None


def build_adaptive_card_activity(
    components: tuple[ComponentRow, ...],
    quick_replies: tuple[QuickReply, ...],
    text: str,
) -> dict[str, object]:
    """Build an Adaptive Card activity payload with interactive actions."""
    actions: list[dict[str, object]] = []

    for row in components:
        for item in row:
            if isinstance(item, ActionButton):
                if item.url:
                    actions.append(
                        {
                            "type": "Action.OpenUrl",
                            "title": item.label,
                            "url": item.url,
                        }
                    )
                else:
                    action: dict[str, object] = {
                        "type": "Action.Submit",
                        "title": item.label,
                        "data": {"action_id": item.action_id, "value": item.value or item.action_id},
                    }
                    if item.style == ButtonStyle.DANGER:
                        action["style"] = "destructive"
                    elif item.style == ButtonStyle.PRIMARY:
                        action["style"] = "positive"
                    actions.append(action)

    for qr in quick_replies:
        actions.append(
            {
                "type": "Action.Submit",
                "title": qr.label,
                "data": {"quick_reply": qr.text},
            }
        )

    card: dict[str, object] = {
        "type": "AdaptiveCard",
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "version": "1.4",
        "body": [{"type": "TextBlock", "text": text, "wrap": True}] if text else [],
        "actions": actions,
    }

    return {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": card,
            }
        ],
    }
