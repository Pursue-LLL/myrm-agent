"""Tests for the numbered-reply fallback of card actions."""

from __future__ import annotations

from app.channels.providers.feishu.action_fallback import (
    FallbackActionSessionRegistry,
    build_fallback_action_card_elements,
)
from app.channels.types import ActionButton


def test_fallback_action_session_registry() -> None:
    registry = FallbackActionSessionRegistry(ttl_seconds=60)
    btn1 = ActionButton(action_id="act_approve", label="批准执行")
    btn2 = ActionButton(action_id="act_deny", label="拒绝授权")

    options = registry.register_actions(
        chat_id="chat_1001",
        user_id="user_2002",
        message_id="msg_3003",
        actions=[btn1, btn2],
    )
    assert len(options) == 2
    assert options[0].index == 1
    assert options[0].action_id == "act_approve"

    # Card elements generation
    card_elems = build_fallback_action_card_elements(options)
    assert len(card_elems) == 2
    assert "[1]" in str(card_elems[1])

    # Resolve with '1'
    res = registry.resolve_action("chat_1001", "user_2002", "1")
    assert res == "act_approve"

    # Session consumed, second resolve should return None
    res2 = registry.resolve_action("chat_1001", "user_2002", "1")
    assert res2 is None


def test_fallback_action_resolution_formats() -> None:
    registry = FallbackActionSessionRegistry(ttl_seconds=60)
    btn1 = ActionButton(action_id="opt_1", label="Option 1")
    btn2 = ActionButton(action_id="opt_2", label="Option 2")

    registry.register_actions("chat_1", "user_1", "msg_1", [btn1, btn2])
    assert registry.resolve_action("chat_1", "user_1", "[2]") == "opt_2"

    registry.register_actions("chat_1", "user_1", "msg_1", [btn1, btn2])
    assert registry.resolve_action("chat_1", "user_1", "【1】") == "opt_1"

    registry.register_actions("chat_1", "user_1", "msg_1", [btn1, btn2])
    assert registry.resolve_action("chat_1", "user_1", "二") == "opt_2"
