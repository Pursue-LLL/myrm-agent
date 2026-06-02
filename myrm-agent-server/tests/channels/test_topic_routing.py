"""Unit tests for per-topic Agent routing.

Tests TopicContext, TopicManager protocol, session key isolation,
agent_id based topic routing, and /bind /unbind /topic command parsing.
"""

from __future__ import annotations

import re

import pytest

from app.channels.routing.command_defs import CommandAction
from app.channels.routing.command_registry import CommandRegistry
from app.channels.routing.commands import TopicCommand, parse_topic_args


def _parse_topic_command(content: str) -> TopicCommand | None:
    """Compat wrapper: resolve topic commands via the registry + parse_topic_args."""
    registry = CommandRegistry()
    resolved = registry.resolve(content)
    if resolved is None:
        return None
    action = resolved.command_def.action
    if action == CommandAction.BIND:
        return parse_topic_args("bind", resolved.raw_args)
    if action == CommandAction.UNBIND:
        return parse_topic_args("unbind", resolved.raw_args)
    if action == CommandAction.TOPIC:
        return parse_topic_args("topic", resolved.raw_args)
    return None
from app.channels.types import InboundMessage, TopicContext  # noqa: E402

# ---------------------------------------------------------------------------
# TopicContext
# ---------------------------------------------------------------------------


class TestTopicContext:
    def test_defaults(self) -> None:
        ctx = TopicContext(topic_id="42")
        assert ctx.topic_id == "42"
        assert ctx.agent_id is None
        assert ctx.enabled is True

    def test_disabled(self) -> None:
        ctx = TopicContext(topic_id="42", enabled=False)
        assert not ctx.enabled

    def test_frozen(self) -> None:
        ctx = TopicContext(topic_id="42")
        with pytest.raises(AttributeError):
            ctx.topic_id = "99"  # type: ignore[misc]

    def test_with_agent_id(self) -> None:
        ctx = TopicContext(topic_id="42", agent_id="agent-uuid-123")
        assert ctx.agent_id == "agent-uuid-123"


# ---------------------------------------------------------------------------
# Session Key Isolation
# ---------------------------------------------------------------------------

_SAFE_CHARS = re.compile(r"[^a-zA-Z0-9_-]")


def _build_session_key_standalone(msg: InboundMessage, user_id: str) -> str:
    """Mirror of agent_executor._build_session_key for isolated testing."""
    raw = msg.chat_id if msg.chat_id else msg.sender_id
    sanitized = _SAFE_CHARS.sub("_", raw) if raw else f"channel-{msg.channel}"
    key = f"user_{user_id}_chat_{sanitized}"
    if msg.thread_id:
        topic = _SAFE_CHARS.sub("_", msg.thread_id)
        key = f"{key}_topic_{topic}"
    return key.lower()


def _inbound(
    channel: str = "telegram",
    chat_id: str = "-1001234567890",
    thread_id: str | None = None,
) -> InboundMessage:
    return InboundMessage(
        channel=channel,
        sender_id="user1",
        content="hello",
        chat_id=chat_id,
        is_group=True,
        thread_id=thread_id,
    )


class TestSessionKeyIsolation:
    def test_no_thread_id(self) -> None:
        msg = _inbound()
        key = _build_session_key_standalone(msg, "u1")
        assert "topic" not in key

    def test_with_thread_id(self) -> None:
        msg = _inbound(thread_id="42")
        key = _build_session_key_standalone(msg, "u1")
        assert "_topic_42" in key

    def test_different_topics_different_keys(self) -> None:
        k1 = _build_session_key_standalone(_inbound(thread_id="10"), "u1")
        k2 = _build_session_key_standalone(_inbound(thread_id="20"), "u1")
        assert k1 != k2

    def test_same_topic_same_key(self) -> None:
        k1 = _build_session_key_standalone(_inbound(thread_id="10"), "u1")
        k2 = _build_session_key_standalone(_inbound(thread_id="10"), "u1")
        assert k1 == k2

    def test_thread_id_sanitized(self) -> None:
        msg = _inbound(thread_id="topic/with spaces@special")
        key = _build_session_key_standalone(msg, "u1")
        assert "/" not in key
        assert " " not in key
        assert "@" not in key

    def test_key_lowercase(self) -> None:
        msg = _inbound(chat_id="Group-ABC", thread_id="Topic-XYZ")
        key = _build_session_key_standalone(msg, "UserA")
        assert key == key.lower()


# ---------------------------------------------------------------------------
# TopicManager Protocol Compliance
# ---------------------------------------------------------------------------


class TestTopicManagerProtocol:
    def test_protocol_check(self) -> None:
        from app.channels.protocols.topic import TopicManager

        class MockManager:
            async def resolve_topic(self, channel: str, chat_id: str, thread_id: str | None) -> TopicContext | None:
                return TopicContext(topic_id=thread_id or chat_id)

            async def bind_topic(
                self, channel: str, chat_id: str, thread_id: str | None, *, agent_id: str | None = None
            ) -> TopicContext:
                return TopicContext(topic_id=thread_id or chat_id, agent_id=agent_id)

            async def sync_topic_metadata(
                self,
                channel: str,
                chat_id: str,
                thread_id: str | None,
                *,
                display_name: str | None = None,
                avatar_url: str | None = None,
            ) -> None:
                pass

            async def unbind_topic(self, channel: str, chat_id: str, thread_id: str | None) -> bool:
                return True

        assert isinstance(MockManager(), TopicManager)

    def test_non_compliant_rejected(self) -> None:
        from app.channels.protocols.topic import TopicManager

        class BadResolver:
            pass

        assert not isinstance(BadResolver(), TopicManager)


# ---------------------------------------------------------------------------
# Agent ID Routing Logic
# ---------------------------------------------------------------------------


class TestAgentIdRouting:
    """Test that TopicContext correctly carries agent_id for routing."""

    def test_no_agent_id_uses_default(self) -> None:
        ctx = TopicContext(topic_id="42")
        assert ctx.agent_id is None

    def test_agent_id_specified(self) -> None:
        ctx = TopicContext(topic_id="42", agent_id="support-agent")
        assert ctx.agent_id == "support-agent"

    def test_disabled_topic_with_agent_id(self) -> None:
        ctx = TopicContext(topic_id="42", agent_id="support-agent", enabled=False)
        assert not ctx.enabled
        assert ctx.agent_id == "support-agent"

    def test_different_topics_different_agents(self) -> None:
        tech = TopicContext(topic_id="10", agent_id="tech-agent")
        news = TopicContext(topic_id="20", agent_id="news-agent")
        assert tech.agent_id != news.agent_id


# ---------------------------------------------------------------------------
# Topic Command Parsing
# ---------------------------------------------------------------------------


class TestTopicCommandParsing:
    def test_bind_no_agent(self) -> None:
        cmd = _parse_topic_command("/bind")
        assert cmd is not None
        assert cmd.action == "bind"
        assert cmd.agent_id is None

    def test_bind_with_agent(self) -> None:
        cmd = _parse_topic_command("/bind support-agent")
        assert cmd is not None
        assert cmd.action == "bind"
        assert cmd.agent_id == "support-agent"

    def test_bind_case_insensitive(self) -> None:
        cmd = _parse_topic_command("/BIND my-agent")
        assert cmd is not None
        assert cmd.action == "bind"
        assert cmd.agent_id == "my-agent"

    def test_unbind(self) -> None:
        cmd = _parse_topic_command("/unbind")
        assert cmd is not None
        assert cmd.action == "unbind"
        assert cmd.agent_id is None

    def test_topic_query(self) -> None:
        cmd = _parse_topic_command("/topic")
        assert cmd is not None
        assert cmd.action == "topic"

    def test_non_topic_command(self) -> None:
        assert _parse_topic_command("/stop") is None
        assert _parse_topic_command("hello") is None
        assert _parse_topic_command("") is None

    def test_whitespace_handling(self) -> None:
        cmd = _parse_topic_command("  /bind  tech-agent  ")
        assert cmd is not None
        assert cmd.agent_id == "tech-agent"

    def test_bound_at_field(self) -> None:
        ctx = TopicContext(topic_id="42", bound_at="2026-03-06T10:00:00")
        assert ctx.bound_at == "2026-03-06T10:00:00"

    def test_bound_at_default_none(self) -> None:
        ctx = TopicContext(topic_id="42")
        assert ctx.bound_at is None


# ---------------------------------------------------------------------------
# TopicContext.matched_by
# ---------------------------------------------------------------------------


class TestMatchedBy:
    def test_default_none(self) -> None:
        ctx = TopicContext(topic_id="42")
        assert ctx.matched_by is None

    def test_thread_binding(self) -> None:
        ctx = TopicContext(topic_id="42", matched_by="thread_binding")
        assert ctx.matched_by == "thread_binding"

    def test_channel_binding(self) -> None:
        ctx = TopicContext(topic_id="42", matched_by="channel_binding")
        assert ctx.matched_by == "channel_binding"

    def test_alias(self) -> None:
        ctx = TopicContext(topic_id="42", matched_by="alias")
        assert ctx.matched_by == "alias"

    def test_frozen_matched_by(self) -> None:
        ctx = TopicContext(topic_id="42", matched_by="alias")
        with pytest.raises(AttributeError):
            ctx.matched_by = "other"  # type: ignore[misc]

    def test_replace_matched_by(self) -> None:
        import dataclasses

        ctx = TopicContext(topic_id="42", agent_id="a1")
        updated = dataclasses.replace(ctx, matched_by="thread_binding")
        assert updated.matched_by == "thread_binding"
        assert updated.agent_id == "a1"
        assert ctx.matched_by is None
