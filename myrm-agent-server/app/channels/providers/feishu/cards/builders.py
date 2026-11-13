"""[INPUT]
- app.channels.providers.feishu.cards.actions::build_card_actions (POS: 飞书卡片子包的一部分；由 __init__.py 聚合导出。)

[OUTPUT]
- build_component_card: Build a Feishu Interactive Card from OutboundMessage components.
- wrap_text_as_card: Wrap arbitrary text in a minimal card; the placeholder, the progress edits and any plain-text edit use it.
- CARD_CONFIG: Config shared by every card the channel sends.
- _format_cost_note: Format cost_metadata into a compact note string for Feishu cards.
- build_result_card: Final result card with optional header, numbered sources, and timestamp.

[POS]
飞书卡片子包的一部分；由 __init__.py 聚合导出。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.channels.providers.feishu.cards.actions import build_card_actions

if TYPE_CHECKING:
    from app.channels.types import (
        OutboundMessage,
    )

# Feishu updates a card in place only if its config sets ``update_multi`` both before and after the update.
CARD_CONFIG: dict[str, object] = {"wide_screen_mode": True, "enable_forward": True, "update_multi": True}

_HEADER_TEMPLATES: dict[bool | None, tuple[str, str]] = {
    True: ("green", ""),
    False: ("red", ""),
    None: ("blue", ""),
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

    return {"config": CARD_CONFIG, "elements": elements}


# ── Placeholder / progress card ──────────────────────────────────


def wrap_text_as_card(text: str) -> dict[str, object]:
    """Wrap arbitrary text in a minimal card.

    The placeholder, every progress edit and any plain-text edit use it, so the whole placeholder lifecycle
    (placeholder → progress → result) stays one interactive card.
    """
    return {
        "config": CARD_CONFIG,
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
    """Final result card with optional header, sources numbered like the citations in ``content``, and timestamp."""
    elements: list[dict[str, object]] = []

    if content:
        elements.append({"tag": "div", "text": {"tag": "lark_md", "content": content}})

    if sources:
        elements.append({"tag": "hr"})
        source_lines = [
            f"[{s.get('index', i)}] [{s.get('title', s.get('url', 'source'))}]({s['url']})"
            for i, s in enumerate(sources, start=1)
            if s.get("url")
        ]
        if source_lines:
            elements.append(
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "**Sources**\n" + "\n".join(source_lines[:10]),
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

    card: dict[str, object] = {"config": CARD_CONFIG, "elements": elements}
    if header:
        card["header"] = header
    return card


# ── Interactive component builders ───────────────────────────────
