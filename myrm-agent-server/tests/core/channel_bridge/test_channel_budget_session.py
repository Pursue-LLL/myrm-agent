"""Unit tests for _resolve_peer and build_channel_budget_key in session.py."""

from __future__ import annotations

from dataclasses import replace

import pytest

from app.channels.types import InboundMessage
from app.core.channel_bridge.agent_executor.session import (
    _build_session_key,
    _resolve_peer,
    build_channel_budget_key,
)
from tests.support.channel_budget_fixtures import GROUP_IDS


def _msg(
    *,
    channel: str = "telegram",
    sender_id: str = "user-1",
    chat_id: str = "chat-1",
    is_group: bool = True,
) -> InboundMessage:
    return InboundMessage(
        channel=channel,
        sender_id=sender_id,
        chat_id=chat_id,
        content="test",
        is_group=is_group,
        sent_at=1.0,
        sent_timezone="UTC",
    )


class TestResolvePeer:
    def test_group_uses_chat_id(self) -> None:
        msg = _msg(is_group=True, chat_id="grp-42")
        kind, pid = _resolve_peer(msg)
        assert kind == "group"
        assert pid == "grp-42"

    def test_dm_uses_sender_id(self) -> None:
        msg = _msg(is_group=False, sender_id="bob")
        kind, pid = _resolve_peer(msg)
        assert kind == "dm"
        assert pid == "bob"

    def test_group_without_chat_id_falls_back_to_sender(self) -> None:
        msg = _msg(is_group=True, chat_id="", sender_id="alice")
        kind, pid = _resolve_peer(msg)
        assert kind == "group"
        assert pid == "alice"

    def test_fallback_when_both_empty(self) -> None:
        msg = _msg(is_group=True, chat_id="", sender_id="")
        kind, pid = _resolve_peer(msg)
        assert kind == "group"
        assert pid == "channel-telegram"

    def test_dm_without_sender_falls_back_to_channel(self) -> None:
        msg = _msg(is_group=False, chat_id="", sender_id="")
        kind, pid = _resolve_peer(msg)
        assert kind == "dm"
        assert pid == "channel-telegram"


class TestBuildChannelBudgetKey:
    def test_group_returns_formatted_key(self) -> None:
        msg = _msg(channel="telegram", is_group=True, chat_id="Chat-99")
        key = build_channel_budget_key(msg)
        assert key == "telegram:group:chat-99"

    def test_dm_returns_empty_string(self) -> None:
        msg = _msg(is_group=False)
        key = build_channel_budget_key(msg)
        assert key == ""

    def test_key_format_matches_session_key_prefix(self) -> None:
        """Ensure budget key prefix matches SessionKey.to_str() prefix."""
        msg = _msg(channel="slack", is_group=True, chat_id="C123")
        budget_key = build_channel_budget_key(msg)
        session_key = _build_session_key(msg)
        assert session_key.startswith(budget_key)

    def test_slack_channel_key(self) -> None:
        msg = _msg(channel="slack", is_group=True, chat_id="C0123ABC")
        key = build_channel_budget_key(msg)
        assert key == "slack:group:c0123abc"

    def test_group_fallback_no_chat_id(self) -> None:
        msg = _msg(channel="discord", is_group=True, chat_id="", sender_id="user-x")
        key = build_channel_budget_key(msg)
        assert key == "discord:group:user-x"

    def test_group_fallback_both_empty(self) -> None:
        msg = _msg(channel="line", is_group=True, chat_id="", sender_id="")
        key = build_channel_budget_key(msg)
        assert key == "line:group:channel-line"

    def test_key_is_always_lowercase(self) -> None:
        """Budget key must be lowercased to match SessionKey.to_str()."""
        msg = _msg(channel="Telegram", is_group=True, chat_id="Chat-ABC")
        key = build_channel_budget_key(msg)
        assert key == key.lower()

    @pytest.mark.parametrize(("channel", "peer"), GROUP_IDS)
    def test_key_is_the_session_key_of_the_group(self, channel: str, peer: str) -> None:
        """Punctuated and capitalised chat ids are sanitised exactly as in the stored session key."""
        msg = _msg(channel=channel, chat_id=peer, is_group=True)

        assert build_channel_budget_key(msg) == _build_session_key(msg)

    @pytest.mark.parametrize(("channel", "peer"), GROUP_IDS)
    def test_key_prefixes_the_session_key_of_every_topic_and_agent_of_the_group(self, channel: str, peer: str) -> None:
        msg = replace(_msg(channel=channel, chat_id=peer, is_group=True), thread_id="T-9")

        assert _build_session_key(msg, agent_id="a1") == f"{build_channel_budget_key(msg)}:thread:t-9:agent:a1"
