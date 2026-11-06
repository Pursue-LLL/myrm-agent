"""[INPUT]
- app.channels.providers.feishu.cards.actions::build_card_actions (POS: 飞书卡片子包的一部分；由 __init__.py 聚合导出。)

[OUTPUT]
- build_component_card: Build a Feishu Interactive Card from OutboundMessage components.
- build_thinking_card: Placeholder card shown while agent is processing.
- wrap_text_as_card: Wrap arbitrary text in a minimal card for consistent edit formatting.
- _format_cost_note: Format cost_metadata into a compact note string for Feishu cards.
- build_result_card: Final result card with optional header, sources, and timestamp.

[POS]
飞书卡片子包的一部分；由 __init__.py 聚合导出。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from app.channels.providers.feishu.cards.actions import build_card_actions

if TYPE_CHECKING:
    from app.channels.types import (
        OutboundMessage,
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


def build_component_card(
    msg: OutboundMessage,
    text: str,
    *,
    fallback_options: list[dict[str, object]] | None = None,
) -> dict[str, object] | None:
    """Build a Feishu Interactive Card from OutboundMessage components.

    Maps Myrm component types to Feishu Card elements:
    - ActionButton → Card button (tag: "button")
    - SelectMenu  → Card select_static (tag: "select_static")
    - QuickReply  → Card button with callback value

    Returns None if no interactive elements are present.
    """
    if not msg.components and not msg.quick_replies and not fallback_options:
        return None

    elements: list[dict[str, object]] = []
    if text:
        elements.append({"tag": "markdown", "content": text})

    action_elements = build_card_actions(msg.quick_replies, msg.components)
    elements.extend(action_elements)

    if fallback_options:
        elements.extend(fallback_options)

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


def _format_cost_note(cost_meta: dict[str, object]) -> str:
    """Format cost_metadata into a compact note string for Feishu cards."""
    cost_usd = cost_meta.get("cost_usd")
    if not isinstance(cost_usd, (int, float)) or cost_usd <= 0:
        return ""

    parts: list[str] = []
    model_name = cost_meta.get("model_name")
    if isinstance(model_name, str) and model_name:
        parts.append(model_name)

    total_tokens = cost_meta.get("total_tokens")
    if isinstance(total_tokens, int) and total_tokens > 0:
        if total_tokens >= 1000:
            parts.append(f"{total_tokens / 1000:.1f}k tokens")
        else:
            parts.append(f"{total_tokens} tokens")

    parts.append(f"~${cost_usd:.4f}")
    return " · ".join(parts)


def build_result_card(
    content: str,
    *,
    title: str = "",
    sources: list[dict[str, object]] | None = None,
    success: bool | None = None,
    timestamp: str = "",
    cost_metadata: dict[str, object] | None = None,
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

    note_parts: list[str] = []
    if timestamp:
        note_parts.append(timestamp)

    if cost_metadata and isinstance(cost_metadata, dict):
        cost_line = _format_cost_note(cost_metadata)
        if cost_line:
            note_parts.append(cost_line)

    if note_parts:
        elements.append(
            {
                "tag": "note",
                "elements": [{"tag": "plain_text", "content": " · ".join(note_parts)}],
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
