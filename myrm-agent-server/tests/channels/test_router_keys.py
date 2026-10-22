"""Router state-map keys: a Telegram topic that binds its own agent must not share state.

The regression these hold down: the router's in-memory maps (active task, /stop target, YOLO
flag, pending approval, debounce queue) were keyed by channel + peer only. Two topics of one
supergroup therefore produced the same key, so answering in topic B overwrote topic A's
running task and `/stop` in A cancelled B.
"""

from __future__ import annotations

from app.channels.routing.router_keys import routing_session_key, routing_state_key


def test_state_key_without_topic_matches_legacy_format() -> None:
    """DMs and untopiced chats keep the historical key, so their state is not reset."""
    assert routing_state_key("telegram", "123") == "telegram:123"
    assert routing_state_key("telegram", "123", None) == "telegram:123"
    assert routing_state_key("telegram", "123", "") == "telegram:123"
    assert routing_state_key("telegram", "123", "   ") == "telegram:123"


def test_state_key_separates_topics_of_one_group() -> None:
    chat_id = "-1001234"
    sales = routing_state_key("telegram", chat_id, "100")
    support = routing_state_key("telegram", chat_id, "200")

    assert sales != support
    assert sales == "telegram:-1001234:100"
    assert support == "telegram:-1001234:200"


def test_state_key_separates_same_topic_across_groups() -> None:
    """The same thread id in two groups stays distinct."""
    assert routing_state_key("telegram", "-1001111", "42") != routing_state_key("telegram", "-1002222", "42")


def test_state_key_keeps_empty_peer() -> None:
    assert routing_state_key("x", "", None) == "x:"


def test_legacy_session_key_still_available() -> None:
    """Chat-wide lookups keep their helper; it deliberately carries no topic."""
    assert routing_session_key("telegram", "123") == "telegram:123"
