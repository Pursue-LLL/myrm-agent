"""Feishu card builders, post format builders, and streaming text utilities.

Pure functions for building Feishu card/post JSON structures, merging
streaming text fragments, and resolving message send modes.

[INPUT]
- app.channels.types::ActionButton, (POS: Provides ArtifactInfo, infer_language, infer_artifact_type.)
- app.channels.types.components::ButtonStyle, (POS: UI component type definitions Cross-channel interactive component abstractions  Support in)

[OUTPUT]
- build_component_card: Build a Feishu Interactive Card from OutboundMessage comp...
- build_thinking_card: Placeholder card shown while agent is processing.
- wrap_text_as_card: Wrap arbitrary text in a minimal card for consistent edit...
- build_result_card: Final result card with optional header, sources, and time...
- build_card_actions: Build Feishu card action elements from QuickReplies and C...

[POS]
Feishu card builders, post format builders, and streaming text utilities.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from app.channels.types import (
        ActionButton,
        OutboundMessage,
        QuickReply,
        SelectMenu,
    )

SendMode = Literal["reply", "root_create", "create"]

_CARD_CONFIG: dict[str, object] = {"wide_screen_mode": True, "enable_forward": True}
_ACTION_VALUE_MAX = 200

_HEADER_TEMPLATES: dict[bool | None, tuple[str, str]] = {
    True: ("green", ""),
    False: ("red", ""),
    None: ("blue", ""),
}

_FEISHU_BUTTON_TYPE: dict[str, str] = {
    "primary": "primary",
    "danger": "danger",
    "default": "default",
}


# ── Component card (from OutboundMessage) ────────────────────────


def build_component_card(msg: OutboundMessage, text: str) -> dict[str, object] | None:
    """Build a Feishu Interactive Card from OutboundMessage components.

    Maps Myrm component types to Feishu Card elements:
    - ActionButton → Card button (tag: "button")
    - SelectMenu  → Card select_static (tag: "select_static")
    - QuickReply  → Card button with callback value

    Returns None if no interactive elements are present.
    """
    if not msg.components and not msg.quick_replies:
        return None

    elements: list[dict[str, object]] = []
    if text:
        elements.append({"tag": "markdown", "content": text})

    action_elements = build_card_actions(msg.quick_replies, msg.components)
    elements.extend(action_elements)

    return {"config": _CARD_CONFIG, "elements": elements}


# ── Thinking / placeholder card ──────────────────────────────────


def build_thinking_card(
    label: str = " Thinking...",
    *,
    card_id: str = "",
) -> dict[str, object]:
    """Placeholder card shown while agent is processing.

    When *card_id* is provided, the card is configured for CardKit streaming
    so the server can push incremental content updates.
    """
    elements: list[dict[str, object]] = [
        {"tag": "div", "text": {"tag": "lark_md", "content": label}},
    ]
    if card_id:
        elements.append({"tag": "streaming_content"})
    card: dict[str, object] = {"config": _CARD_CONFIG, "elements": elements}
    if card_id:
        card["card_id"] = card_id
    return card


def wrap_text_as_card(text: str) -> dict[str, object]:
    """Wrap arbitrary text in a minimal card for consistent edit formatting.

    Used by edit_message to keep the entire placeholder lifecycle
    as interactive cards (thinking → progress → result).
    """
    return {
        "config": _CARD_CONFIG,
        "elements": [
            {"tag": "div", "text": {"tag": "lark_md", "content": text}},
        ],
    }


# ── Result card ──────────────────────────────────────────────────


def build_result_card(
    content: str,
    *,
    title: str = "",
    sources: list[dict[str, object]] | None = None,
    success: bool | None = None,
    timestamp: str = "",
) -> dict[str, object]:
    """Final result card with optional header, sources, and timestamp."""
    elements: list[dict[str, object]] = []

    if content:
        elements.append({"tag": "div", "text": {"tag": "lark_md", "content": content}})

    if sources:
        elements.append({"tag": "hr"})
        source_lines = [f"[{s.get('title', s.get('url', 'source'))}]({s['url']})" for s in sources if s.get("url")]
        if source_lines:
            elements.append(
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "**refusesource: **\n" + "\n".join(source_lines[:10]),
                    },
                }
            )

    if timestamp:
        elements.append(
            {
                "tag": "note",
                "elements": [{"tag": "plain_text", "content": timestamp}],
            }
        )

    header: dict[str, object] | None = None
    if title or success is not None:
        template, icon = _HEADER_TEMPLATES.get(success, _HEADER_TEMPLATES[None])
        header_title = f"{icon} {title}" if title else f"{icon} Notification"
        header = {
            "title": {"tag": "plain_text", "content": header_title},
            "template": template,
        }

    card: dict[str, object] = {"config": _CARD_CONFIG, "elements": elements}
    if header:
        card["header"] = header
    return card


# ── Interactive component builders ───────────────────────────────


def build_card_actions(
    quick_replies: tuple[QuickReply, ...] = (),
    components: tuple[tuple[ActionButton | SelectMenu, ...], ...] = (),
) -> list[dict[str, object]]:
    """Build Feishu card action elements from QuickReplies and Components.

    Returns a list of card elements (action blocks) to append to card['elements'].
    Returns empty list if no interactive elements.
    """
    from app.channels.types import ActionButton
    from app.channels.types.components import (
        ButtonStyle,
        SelectMenu,
    )

    actions: list[dict[str, object]] = []

    for qr in quick_replies:
        actions.append(
            {
                "tag": "button",
                "text": {"tag": "plain_text", "content": qr.label},
                "type": "default",
                "value": {"type": "qr", "data": qr.text[:_ACTION_VALUE_MAX]},
            }
        )

    for row in components:
        for comp in row:
            if isinstance(comp, ActionButton):
                btn_type = _FEISHU_BUTTON_TYPE.get(
                    comp.style.value if isinstance(comp.style, ButtonStyle) else str(comp.style),
                    "default",
                )
                btn: dict[str, object] = {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": comp.label},
                    "type": btn_type,
                    "value": {"type": "act", "action_id": comp.action_id[:_ACTION_VALUE_MAX]},
                }
                if comp.url:
                    btn["url"] = comp.url
                actions.append(btn)
            elif isinstance(comp, SelectMenu):
                options = [
                    {
                        "text": {"tag": "plain_text", "content": opt.label},
                        "value": f"sel:{opt.value[:_ACTION_VALUE_MAX]}",
                    }
                    for opt in comp.options
                ]
                actions.append(
                    {
                        "tag": "select_static",
                        "placeholder": {"tag": "plain_text", "content": comp.placeholder},
                        "options": options,
                        "value": {
                            "type": "sel",
                            "action_id": comp.action_id[:_ACTION_VALUE_MAX],
                        },
                    }
                )

    if not actions:
        return []
    return [{"tag": "action", "actions": actions}]


# ── Card callback parsing ────────────────────────────────────────


def parse_card_action(
    event: dict[str, object],
) -> tuple[str, str, str, dict[str, object]] | None:
    """Parse a Feishu card.action.trigger event into structured callback data.

    Returns (sender_open_id, chat_id, content, metadata) or None if unparseable.

    Callback data prefixes:
    - ``qr:text`` → QuickReply click
    - ``act:action_id`` → ActionButton click
    - ``sel:value`` → SelectMenu pick
    """
    operator = event.get("operator")
    if not isinstance(operator, dict):
        return None
    sender_open_id = str(operator.get("open_id", ""))

    action = event.get("action")
    if not isinstance(action, dict):
        return None

    value = action.get("value")
    if not isinstance(value, dict):
        return None

    action_type = str(value.get("type", ""))
    content = ""
    if action_type == "qr":
        content = str(value.get("data", ""))
    elif action_type == "act":
        content = str(value.get("action_id", ""))
    elif action_type == "sel":
        option = action.get("option")
        if isinstance(option, str) and option.startswith("sel:"):
            content = option[4:]
        else:
            content = str(value.get("action_id", ""))

    context = event.get("context")
    chat_id = ""
    message_id = ""
    if isinstance(context, dict):
        chat_id = str(context.get("open_chat_id", ""))
        message_id = str(context.get("open_message_id", ""))

    metadata: dict[str, object] = {
        "callback_type": action_type,
        "card_message_id": message_id,
        "action_tag": action.get("tag"),
    }

    return sender_open_id, chat_id, content, metadata


# ── Streaming text merge ─────────────────────────────────────────


def merge_streaming_text(previous: str, next_chunk: str) -> str:
    """Merge streaming text fragments with correct precedence.

    Priority: full containment > partial overlap > fallback append.
    """
    if not previous:
        return next_chunk
    if not next_chunk:
        return previous

    if next_chunk.startswith(previous):
        return next_chunk
    if previous.startswith(next_chunk):
        return previous
    if next_chunk in previous:
        return previous
    if previous in next_chunk:
        return next_chunk

    max_overlap = min(len(previous), len(next_chunk))
    for overlap in range(max_overlap, 0, -1):
        if previous.endswith(next_chunk[:overlap]):
            return f"{previous}{next_chunk[overlap:]}"

    return f"{previous}{next_chunk}"


# ── Send mode resolution ─────────────────────────────────────────


def resolve_send_mode(
    *,
    reply_to_id: str | None = None,
    root_id: str | None = None,
) -> SendMode:
    """Determine Feishu message send mode based on context.

    Priority: reply > root_create > create.
    """
    if reply_to_id:
        return "reply"
    if root_id:
        return "root_create"
    return "create"


# ── Post (rich text) format builders ─────────────────────────────

_RICH_TEXT_RE = re.compile(
    r"\*\*.+?\*\*"
    r"|(?<!\w)_.+?_(?!\w)"
    r"|\[.+?\]\(.+?\)"
    r"|~~.+?~~"
    r"|`[^`]+`",
)
_HEADING_RE = re.compile(r"^#{1,6}\s+", re.MULTILINE)
_POST_INLINE_RE = re.compile(
    r"(\*\*(.+?)\*\*)"
    r"|(~~(.+?)~~)"
    r"|(`([^`]+)`)"
    r"|(\[(.+?)\]\((.+?)\))",
)


def has_rich_text(content: str) -> bool:
    """Detect if content has rich formatting that benefits from post type."""
    return bool(_RICH_TEXT_RE.search(content) or _HEADING_RE.search(content))


def _parse_post_line(line: str) -> list[dict[str, object]]:
    """Parse a single line of Markdown into Feishu post elements."""
    elements: list[dict[str, object]] = []
    pos = 0
    for m in _POST_INLINE_RE.finditer(line):
        if m.start() > pos:
            elements.append({"tag": "text", "text": line[pos : m.start()]})
        if m.group(2) is not None:
            elements.append({"tag": "text", "text": m.group(2), "style": ["bold"]})
        elif m.group(4) is not None:
            elements.append({"tag": "text", "text": m.group(4), "style": ["lineThrough"]})
        elif m.group(6) is not None:
            elements.append({"tag": "text", "text": m.group(6), "style": ["code"]})
        elif m.group(8) is not None:
            elements.append({"tag": "a", "text": m.group(8), "href": m.group(9)})
        pos = m.end()
    if pos < len(line):
        elements.append({"tag": "text", "text": line[pos:]})
    return elements or [{"tag": "text", "text": line}]


def build_post_content(content: str) -> dict[str, object]:
    """Convert Markdown-like text to Feishu post (rich text) format.

    Produces a post payload with zh_cn locale. Handles bold, italic,
    inline code, links, and headings by mapping to Feishu post tags.
    """
    paragraphs: list[list[dict[str, object]]] = []
    for line in content.split("\n"):
        elements: list[dict[str, object]] = []
        heading_match = _HEADING_RE.match(line)
        if heading_match:
            line = line[heading_match.end() :]
            elements.append({"tag": "text", "text": line, "style": ["bold"]})
        else:
            elements.extend(_parse_post_line(line))
        paragraphs.append(elements)
    return {"zh_cn": {"title": "", "content": paragraphs}}
