"""Tests for channel executor quick-reply helpers."""

from __future__ import annotations

from app.core.channel_bridge.executor_helpers.quick_replies import (
    extract_external_agents,
    suggest_quick_replies,
)


def test_extract_external_agents_returns_none_for_empty() -> None:
    assert extract_external_agents(None) is None
    assert extract_external_agents({}) is None


def test_extract_external_agents_returns_none_for_invalid_agents() -> None:
    assert extract_external_agents({"agents": "not-a-list"}) is None


def test_extract_external_agents_returns_agents_list() -> None:
    agents = [{"id": "a1"}]
    assert extract_external_agents({"agents": agents}) == agents


def test_suggest_quick_replies_only_on_first_message() -> None:
    first = suggest_quick_replies(is_first_message=True)
    later = suggest_quick_replies(is_first_message=False)
    assert len(first) > 0
    assert later == ()
