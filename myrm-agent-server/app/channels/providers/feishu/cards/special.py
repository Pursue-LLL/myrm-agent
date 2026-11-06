"""[INPUT]
- （无跨模块依赖）

[OUTPUT]
- build_contact_disambiguation_card: Build an interactive disambiguation card when multiple contact candidates match.
- build_deliverable_card: Build an enterprise deliverable handover card.

[POS]
飞书卡片子包的一部分；由 __init__.py 聚合导出。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    pass

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


def build_contact_disambiguation_card(
    query: str,
    candidates: list[dict[str, str]],
    *,
    action_key: str = "select_contact",
) -> dict[str, object]:
    """Build an interactive disambiguation card when multiple contact candidates match.

    Presents candidate buttons with name and department for one-click confirmation.
    """
    elements: list[dict[str, object]] = [
        {
            "tag": "markdown",
            "content": f"🔍 找到了多个与 **{query}** 相似的联系人，请确认目标同事：",
        }
    ]

    actions: list[dict[str, object]] = []
    for cand in candidates[:5]:
        name = cand.get("name", "")
        dept = cand.get("department", "")
        open_id = cand.get("open_id", "")
        label = f"{name} ({dept})" if dept else name

        actions.append(
            {
                "tag": "button",
                "text": {"tag": "plain_text", "content": label},
                "type": "primary",
                "value": {"action": action_key, "open_id": open_id, "name": name},
            }
        )

    if actions:
        elements.append({"tag": "action", "actions": actions})

    return {
        "config": _CARD_CONFIG,
        "header": {
            "template": "blue",
            "title": {"tag": "plain_text", "content": "联系人确认 (Contact Disambiguation)"},
        },
        "elements": elements,
    }


def build_deliverable_card(
    title: str,
    summary: str,
    *,
    file_name: str = "",
    file_url: str = "",
    bitable_url: str = "",
) -> dict[str, object]:
    """Build an enterprise deliverable handover card.

    Includes artifact summary, file download/preview, and online Bitable collaboration links.
    """
    md_content = f"**{title}**\n\n{summary}"
    elements: list[dict[str, object]] = [{"tag": "markdown", "content": md_content}]

    actions: list[dict[str, object]] = []
    if file_url:
        actions.append(
            {
                "tag": "button",
                "text": {"tag": "plain_text", "content": f"📥 查看附件 {file_name}".strip()},
                "type": "primary",
                "url": file_url,
            }
        )
    if bitable_url:
        actions.append(
            {
                "tag": "button",
                "text": {"tag": "plain_text", "content": "📊 打开飞书多维表格"},
                "type": "default",
                "url": bitable_url,
            }
        )

    if actions:
        elements.append({"tag": "action", "actions": actions})

    return {
        "config": _CARD_CONFIG,
        "header": {
            "template": "turquoise",
            "title": {"tag": "plain_text", "content": "💼 工作交付成果 (Deliverable Handoff)"},
        },
        "elements": elements,
    }
