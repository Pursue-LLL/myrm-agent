"""卡片动作按钮的构造与回调解析。

[POS]
飞书卡片子包的一部分；由 __init__.py 聚合导出。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from app.channels.types import (
        ActionButton,
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
                    (comp.style.value if isinstance(comp.style, ButtonStyle) else str(comp.style)),
                    "default",
                )
                btn: dict[str, object] = {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": comp.label},
                    "type": btn_type,
                    "value": {
                        "type": "act",
                        "action_id": comp.action_id[:_ACTION_VALUE_MAX],
                    },
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
                        "placeholder": {
                            "tag": "plain_text",
                            "content": comp.placeholder,
                        },
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
