"""飞书卡片门面。

[OUTPUT]
卡片构造、动作解析、流式文本与特殊卡片函数。

[POS]
`app.channels.providers.feishu.cards` 的唯一入口；实现按卡片职责拆分。
"""

from app.channels.providers.feishu.cards.actions import build_card_actions, parse_card_action
from app.channels.providers.feishu.cards.builders import (
    _format_cost_note,
    build_component_card,
    build_result_card,
    build_thinking_card,
    wrap_text_as_card,
)
from app.channels.providers.feishu.cards.special import (
    build_contact_disambiguation_card,
    build_deliverable_card,
)
from app.channels.providers.feishu.cards.text import (
    build_post_content,
    has_rich_text,
    merge_streaming_text,
    resolve_send_mode,
)

__all__ = [
    "_format_cost_note",
    "build_card_actions",
    "build_component_card",
    "build_contact_disambiguation_card",
    "build_deliverable_card",
    "build_post_content",
    "build_result_card",
    "build_thinking_card",
    "has_rich_text",
    "merge_streaming_text",
    "parse_card_action",
    "resolve_send_mode",
    "wrap_text_as_card",
]
