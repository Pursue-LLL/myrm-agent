"""Slack pure-function helpers — Block Kit builder and inbound event parsing.

All functions are stateless and have no side effects, making them easy to test.

[INPUT]
- app.channels.types::OutboundMessage, ActionButton (POS: Channel domain types.)

[OUTPUT]
- build_blocks: OutboundMessage → Slack Block Kit actions blocks.
- verify_slack_signature: Verify Slack request signature (HMAC-SHA256).
- parse_message_event: raw event dict → InboundMessage | None.
- parse_block_action: Parse a Slack block_actions payload into structured fields.
- strip_mention: Remove <@BOT_ID> mention from message text.
- parse_media_attachments: Extract MediaAttachment list from a Slack message event.

[POS]
app.channels.providers.slack.helpers — Slack pure-function helpers: Block Kit builder and inbound event parsing.
"""

from __future__ import annotations

import hashlib
import hmac
import re

from app.channels.types import (
    ActionButton,
    ButtonStyle,
    MediaAttachment,
    OutboundMessage,
    SelectMenu,
    guess_media_type,
)

_SLACK_BUTTON_STYLE: dict[ButtonStyle, str] = {
    ButtonStyle.PRIMARY: "primary",
    ButtonStyle.DANGER: "danger",
}


def build_blocks(msg: OutboundMessage) -> list[dict[str, object]] | None:
    """Build Slack Block Kit actions blocks from QuickReplies and Components.

    Uses action_id prefix protocol (qr:/act:/sel:) consistent with other channels.
    Slack limits actions blocks to 25 elements; excess elements are truncated.
    Returns None if no interactive elements, letting Slack render plain text.
    """
    elements: list[dict[str, object]] = []

    for qr in msg.quick_replies:
        elements.append(
            {
                "type": "button",
                "text": {"type": "plain_text", "text": qr.label[:75]},
                "action_id": f"qr:{qr.text[:250]}",
                "value": qr.text[:75],
            }
        )

    for row in msg.components:
        for comp in row:
            if isinstance(comp, ActionButton):
                btn: dict[str, object] = {
                    "type": "button",
                    "text": {"type": "plain_text", "text": comp.label[:75]},
                    "action_id": f"act:{comp.action_id[:250]}",
                }
                if comp.url:
                    btn["url"] = comp.url
                else:
                    btn["value"] = comp.value or comp.action_id
                style = _SLACK_BUTTON_STYLE.get(comp.style)
                if style:
                    btn["style"] = style
                elements.append(btn)
            elif isinstance(comp, SelectMenu):
                elements.append(
                    {
                        "type": "static_select",
                        "placeholder": {"type": "plain_text", "text": (comp.placeholder or "Select...")[:150]},
                        "action_id": f"sel:{comp.action_id[:250]}",
                        "options": [
                            {
                                "text": {"type": "plain_text", "text": opt.label[:75]},
                                "value": opt.value[:75],
                            }
                            for opt in comp.options[:100]
                        ],
                    }
                )

    if not elements:
        return None
    return [{"type": "actions", "elements": elements[:25]}]


def verify_slack_signature(signing_secret: str, body: bytes, timestamp: str, signature: str) -> bool:
    """Verify Slack request signature (HMAC-SHA256)."""
    if not signing_secret:
        return True
    basestring = f"v0:{timestamp}:{body.decode('utf-8')}"
    expected = "v0=" + hmac.new(signing_secret.encode(), basestring.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def strip_mention(text: str, bot_user_id: str) -> str:
    """Remove <@BOT_ID> mention from message text."""
    if not text or not bot_user_id:
        return text.strip()
    return re.sub(rf"<@{re.escape(bot_user_id)}>\s*", "", text).strip()


def parse_media_attachments(event: dict[str, object]) -> list[MediaAttachment]:
    """Extract MediaAttachment list from a Slack message event."""
    media_list: list[MediaAttachment] = []
    files = event.get("files")
    if not isinstance(files, list):
        return media_list
    for f in files:
        if not isinstance(f, dict):
            continue
        mime = str(f.get("mimetype", ""))
        fname = str(f.get("name", "file"))
        mt = guess_media_type(fname, mime)
        media_list.append(
            MediaAttachment(
                media_type=mt,
                url=str(f.get("url_private", "")),
                filename=str(f.get("name", "")),
                mime_type=mime,
            )
        )
    return media_list


def parse_block_action(
    payload: dict[str, object],
    bot_user_id: str,
) -> dict[str, object] | None:
    """Parse a Slack block_actions payload into structured fields.

    Returns None if the action should be ignored (e.g. from the bot itself).
    Returns a dict with keys: user_id, channel_id, content, message_ts, metadata.
    """
    user_obj = payload.get("user", {})
    if not isinstance(user_obj, dict):
        return None
    user_id = str(user_obj.get("id", ""))
    if not user_id or user_id == bot_user_id:
        return None

    channel_obj = payload.get("channel", {})
    channel_id = str(channel_obj.get("id", "")) if isinstance(channel_obj, dict) else ""

    actions = payload.get("actions", [])
    if not isinstance(actions, list) or not actions:
        return None

    action = actions[0]
    if not isinstance(action, dict):
        return None

    raw_action_id = str(action.get("action_id", ""))
    action_type = str(action.get("type", ""))

    prefix, _, action_payload = raw_action_id.partition(":")
    if not action_payload:
        action_payload = raw_action_id
        prefix = ""

    if prefix == "sel" or action_type == "static_select":
        selected = action.get("selected_option", {})
        content = str(selected.get("value", action_payload)) if isinstance(selected, dict) else action_payload
    elif prefix == "qr":
        content = action_payload
    else:
        content = action_payload

    message_obj = payload.get("message", {})
    message_ts = str(message_obj.get("ts", "")) if isinstance(message_obj, dict) else ""

    sender_name = str(user_obj.get("name", "")) or None
    return {
        "user_id": user_id,
        "channel_id": channel_id,
        "content": content,
        "message_ts": message_ts,
        "sender_name": sender_name,
        "metadata": {
            "interaction_type": "block_actions",
            "action_id": raw_action_id,
            "action_type": action_type,
            "action_prefix": prefix,
            "trigger_id": str(payload.get("trigger_id", "")),
        },
    }
