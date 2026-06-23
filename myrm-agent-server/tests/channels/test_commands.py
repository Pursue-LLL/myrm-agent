"""Tests for routing/commands.py — pure parsers + async command handlers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.channels.routing.command_defs import (
    CommandAction,
    CommandDef,
    CommandKind,
)
from app.channels.routing.command_registry import (
    CommandRegistry,
)
from app.channels.routing.commands import (
    TopicCommand,
    handle_compact,
    handle_new_session,
    handle_topic_command,
    is_explicit_approval_command,
    parse_approval_command,
    parse_topic_args,
)
from app.channels.types import InboundMessage, OutboundMessage

_TEST_AGENT_ROUTES: tuple[CommandDef, ...] = (
    CommandDef(
        name="claude",
        description="Route to Claude",
        kind=CommandKind.AGENT_ROUTE,
        aliases=("cc",),
        agent_id="claude",
        parse_args=True,
        category="Agent",
    ),
    CommandDef(
        name="codex",
        description="Route to Codex",
        kind=CommandKind.AGENT_ROUTE,
        aliases=("cx",),
        agent_id="codex",
        parse_args=True,
        category="Agent",
    ),
    CommandDef(
        name="cursor",
        description="Route to Cursor",
        kind=CommandKind.AGENT_ROUTE,
        aliases=("cs",),
        agent_id="cursor",
        parse_args=True,
        category="Agent",
    ),
    CommandDef(
        name="kimi",
        description="Route to Kimi",
        kind=CommandKind.AGENT_ROUTE,
        aliases=("km",),
        agent_id="kimi",
        parse_args=True,
        category="Agent",
    ),
    CommandDef(
        name="gemini",
        description="Route to Gemini",
        kind=CommandKind.AGENT_ROUTE,
        aliases=("gm",),
        agent_id="gemini",
        parse_args=True,
        category="Agent",
    ),
    CommandDef(
        name="openclaw",
        description="Route to OpenClaw",
        kind=CommandKind.AGENT_ROUTE,
        aliases=("oc",),
        agent_id="openclaw",
        parse_args=True,
        category="Agent",
    ),
    CommandDef(
        name="opencode",
        description="Route to OpenCode",
        kind=CommandKind.AGENT_ROUTE,
        aliases=("ocd",),
        agent_id="opencode",
        parse_args=True,
        category="Agent",
    ),
)


def _make_registry() -> CommandRegistry:
    """Create a registry with test agent routes."""
    registry = CommandRegistry()
    for cmd in _TEST_AGENT_ROUTES:
        registry.register(cmd)
    return registry


# ── Command resolution tests (replaces old is_xxx tests) ──────────────


class TestCommandResolution:
    def test_stop_exact(self) -> None:
        registry = _make_registry()
        resolved = registry.resolve("/stop")
        assert resolved is not None
        assert resolved.command_def.action == CommandAction.STOP

    def test_stop_case_insensitive(self) -> None:
        registry = _make_registry()
        resolved = registry.resolve("/STOP")
        assert resolved is not None
        assert resolved.command_def.action == CommandAction.STOP

    def test_stop_with_whitespace(self) -> None:
        registry = _make_registry()
        resolved = registry.resolve("  /stop  ")
        assert resolved is not None
        assert resolved.command_def.action == CommandAction.STOP

    def test_not_stop(self) -> None:
        registry = _make_registry()
        assert registry.resolve("/start") is None
        assert registry.resolve("stop") is None

    def test_new_session(self) -> None:
        registry = _make_registry()
        resolved = registry.resolve("/new")
        assert resolved is not None
        assert resolved.command_def.action == CommandAction.NEW_SESSION

    def test_compact(self) -> None:
        registry = _make_registry()
        resolved = registry.resolve("/compact")
        assert resolved is not None
        assert resolved.command_def.action == CommandAction.COMPACT
        assert resolved.raw_args == ""

    def test_compact_with_focus_topic(self) -> None:
        registry = _make_registry()
        resolved = registry.resolve("/compact Focus on API design")
        assert resolved is not None
        assert resolved.command_def.action == CommandAction.COMPACT
        assert resolved.raw_args == "Focus on API design"

    def test_compact_with_chinese_topic(self) -> None:
        registry = _make_registry()
        resolved = registry.resolve("/compact 聚焦API设计决策")
        assert resolved is not None
        assert resolved.raw_args == "聚焦API设计决策"

    def test_help(self) -> None:
        registry = _make_registry()
        resolved = registry.resolve("/help")
        assert resolved is not None
        assert resolved.command_def.action == CommandAction.HELP


class TestParseApprovalCommand:
    def test_approve_once_slash(self) -> None:
        assert parse_approval_command("/approve") == "allow_once"

    def test_approve_once_numeric(self) -> None:
        assert parse_approval_command("1") == "allow_once"

    def test_approve_once_natural_language(self) -> None:
        assert parse_approval_command("y") == "allow_once"
        assert parse_approval_command("yes") == "allow_once"
        assert parse_approval_command("ok") == "allow_once"
        assert parse_approval_command("同意") == "allow_once"
        assert parse_approval_command("好的") == "allow_once"

    def test_approve_always_slash(self) -> None:
        assert parse_approval_command("/approve-always") == "allow_always"
        assert parse_approval_command("/always") == "allow_always"

    def test_approve_always_natural_language(self) -> None:
        assert parse_approval_command("永远允许") == "allow_always"
        assert parse_approval_command("总是允许") == "allow_always"
        assert parse_approval_command("aa") == "allow_always"
        assert parse_approval_command("!y") == "allow_always"

    def test_deny_slash(self) -> None:
        assert parse_approval_command("/deny") == "deny"

    def test_deny_numeric(self) -> None:
        assert parse_approval_command("2") == "deny"

    def test_deny_natural_language(self) -> None:
        assert parse_approval_command("n") == "deny"
        assert parse_approval_command("no") == "deny"
        assert parse_approval_command("拒绝") == "deny"
        assert parse_approval_command("不行") == "deny"

    def test_batch_valid(self) -> None:
        result = parse_approval_command("/batch a,d,a")
        assert result == ["allow_once", "deny", "allow_once"]

    def test_batch_with_reject(self) -> None:
        result = parse_approval_command("/batch r,approve,deny")
        assert result == ["deny", "allow_once", "deny"]

    def test_batch_with_always(self) -> None:
        result = parse_approval_command("/batch aa,a,d")
        assert result == ["allow_always", "allow_once", "deny"]

    def test_batch_empty_spec(self) -> None:
        assert parse_approval_command("/batch ") is None

    def test_batch_invalid_token(self) -> None:
        assert parse_approval_command("/batch a,x,d") is None

    def test_unrecognized(self) -> None:
        assert parse_approval_command("hello") is None

    def test_approve_emoji_thumbs_up(self) -> None:
        assert parse_approval_command("👍") == "allow_once"

    def test_approve_emoji_heart(self) -> None:
        assert parse_approval_command("❤️") == "allow_once"

    def test_approve_emoji_check(self) -> None:
        assert parse_approval_command("✅") == "allow_once"

    def test_approve_emoji_skin_tone(self) -> None:
        assert parse_approval_command("👍🏽") == "allow_once"

    def test_approve_always_emoji_infinity(self) -> None:
        assert parse_approval_command("♾") == "allow_always"
        assert parse_approval_command("♾️") == "allow_always"

    def test_approve_always_emoji_star(self) -> None:
        assert parse_approval_command("⭐") == "allow_always"

    def test_deny_emoji_thumbs_down(self) -> None:
        assert parse_approval_command("👎") == "deny"

    def test_deny_emoji_cross(self) -> None:
        assert parse_approval_command("❌") == "deny"

    def test_deny_emoji_no_entry(self) -> None:
        assert parse_approval_command("🚫") == "deny"

    def test_emoji_not_approval(self) -> None:
        assert parse_approval_command("🎉") is None


class TestIsExplicitApprovalCommand:
    def test_approve(self) -> None:
        assert is_explicit_approval_command("/approve") is True

    def test_approve_always(self) -> None:
        assert is_explicit_approval_command("/approve-always") is True
        assert is_explicit_approval_command("/always") is True

    def test_deny(self) -> None:
        assert is_explicit_approval_command("/deny") is True

    def test_batch(self) -> None:
        assert is_explicit_approval_command("/batch a,d") is True

    def test_numeric_not_explicit(self) -> None:
        assert is_explicit_approval_command("1") is False


class TestParseTopicArgs:
    def test_bind_no_agent(self) -> None:
        result = parse_topic_args("bind", "")
        assert result == TopicCommand(action="bind", agent_id=None)

    def test_bind_with_agent(self) -> None:
        result = parse_topic_args("bind", "my-agent")
        assert result == TopicCommand(action="bind", agent_id="my-agent")

    def test_unbind(self) -> None:
        result = parse_topic_args("unbind", "")
        assert result == TopicCommand(action="unbind")

    def test_topic(self) -> None:
        result = parse_topic_args("topic", "")
        assert result == TopicCommand(action="topic")


class TestAgentRouteCommands:
    def test_known_alias_with_message(self) -> None:
        registry = _make_registry()
        resolved = registry.resolve("/cc hello world")
        assert resolved is not None
        assert resolved.command_def.kind == CommandKind.AGENT_ROUTE
        assert resolved.command_def.agent_id == "claude"
        assert resolved.raw_args == "hello world"

    def test_known_alias_no_message(self) -> None:
        registry = _make_registry()
        resolved = registry.resolve("/gm")
        assert resolved is not None
        assert resolved.command_def.agent_id == "gemini"
        assert resolved.raw_args == ""

    def test_unknown_alias(self) -> None:
        registry = _make_registry()
        assert registry.resolve("/xx test") is None

    def test_all_aliases(self) -> None:
        registry = _make_registry()
        aliases = {
            "cc": "claude",
            "cx": "codex",
            "cs": "cursor",
            "km": "kimi",
            "gm": "gemini",
            "oc": "openclaw",
            "ocd": "opencode",
        }
        for alias, expected_id in aliases.items():
            resolved = registry.resolve(f"/{alias} test")
            assert resolved is not None, f"/{alias} should be recognized"
            assert resolved.command_def.agent_id == expected_id


# ── Async handler tests ───────────────────────────────────────────────


def _make_msg(
    content: str = "",
    channel: str = "test",
    sender_id: str = "user1",
    chat_id: str | None = None,
    is_group: bool = False,
    thread_id: str | None = None,
    user_id: str | None = None,
) -> InboundMessage:
    return InboundMessage(
        channel=channel,
        sender_id=sender_id,
        content=content,
        chat_id=chat_id,
        is_group=is_group,
        thread_id=thread_id,
        user_id=user_id,
    )


def _mock_bus() -> MagicMock:
    bus = MagicMock()
    bus.publish_outbound = AsyncMock()
    bus.get_channel = MagicMock(return_value=None)
    return bus


class TestHandleNewSession:
    @pytest.mark.asyncio
    async def test_marks_peer_and_publishes(self) -> None:
        msg = _make_msg(channel="tg", sender_id="u1")
        bus = _mock_bus()
        peers: dict[str, float] = {}

        await handle_new_session(msg, bus, peers)

        assert len(peers) == 1
        bus.publish_outbound.assert_called_once()
        reply: OutboundMessage = bus.publish_outbound.call_args[0][0]
        assert "New conversation" in reply.content

    @pytest.mark.asyncio
    async def test_uses_chat_id_when_present(self) -> None:
        msg = _make_msg(channel="tg", sender_id="u1", chat_id="group1")
        bus = _mock_bus()
        peers: dict[str, float] = {}

        await handle_new_session(msg, bus, peers)

        reply: OutboundMessage = bus.publish_outbound.call_args[0][0]
        assert reply.recipient_id == "group1"


class TestHandleCompact:
    @pytest.mark.asyncio
    async def test_no_handler_configured(self) -> None:
        msg = _make_msg()
        bus = _mock_bus()
        resolver = MagicMock()

        await handle_compact(msg, bus, resolver, compact_handler=None)

        bus.publish_outbound.assert_called_once()
        reply: OutboundMessage = bus.publish_outbound.call_args[0][0]
        assert "not configured" in reply.content

    @pytest.mark.asyncio
    async def test_dm_compact_success(self) -> None:
        msg = _make_msg(is_group=False)
        bus = _mock_bus()
        resolver = MagicMock()
        resolver.resolve_dm_user = AsyncMock(return_value="uid1")

        result_obj = MagicMock()
        result_obj.compacted = True
        result_obj.message_count = 10
        result_obj.tokens_saved = 500
        handler = AsyncMock(return_value=result_obj)

        await handle_compact(msg, bus, resolver, compact_handler=handler)

        bus.publish_outbound.assert_called_once()
        reply: OutboundMessage = bus.publish_outbound.call_args[0][0]
        assert "compacted" in reply.content.lower()

    @pytest.mark.asyncio
    async def test_dm_compact_skipped(self) -> None:
        msg = _make_msg(is_group=False)
        bus = _mock_bus()
        resolver = MagicMock()
        resolver.resolve_dm_user = AsyncMock(return_value="uid1")

        result_obj = MagicMock()
        result_obj.compacted = False
        result_obj.reason = "too few messages"
        handler = AsyncMock(return_value=result_obj)

        await handle_compact(msg, bus, resolver, compact_handler=handler)

        reply: OutboundMessage = bus.publish_outbound.call_args[0][0]
        assert "skipped" in reply.content.lower()

    @pytest.mark.asyncio
    async def test_dm_no_user(self) -> None:
        msg = _make_msg(is_group=False)
        bus = _mock_bus()
        resolver = MagicMock()
        resolver.resolve_dm_user = AsyncMock(return_value=None)
        handler = AsyncMock()

        await handle_compact(msg, bus, resolver, compact_handler=handler)

        handler.assert_not_called()

    @pytest.mark.asyncio
    async def test_group_compact_success(self) -> None:
        msg = _make_msg(is_group=True)
        bus = _mock_bus()
        resolver = MagicMock()
        resolved_msg = _make_msg(is_group=True, user_id="guser")
        resolver.resolve_group_user = AsyncMock(return_value=("guser", resolved_msg))

        result_obj = MagicMock()
        result_obj.compacted = True
        result_obj.message_count = 5
        result_obj.tokens_saved = 200
        handler = AsyncMock(return_value=result_obj)

        await handle_compact(msg, bus, resolver, compact_handler=handler)

        handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_group_no_user(self) -> None:
        msg = _make_msg(is_group=True)
        bus = _mock_bus()
        resolver = MagicMock()
        resolver.resolve_group_user = AsyncMock(return_value=None)
        handler = AsyncMock()

        await handle_compact(msg, bus, resolver, compact_handler=handler)

        handler.assert_not_called()

    @pytest.mark.asyncio
    async def test_compact_exception(self) -> None:
        msg = _make_msg(is_group=False)
        bus = _mock_bus()
        resolver = MagicMock()
        resolver.resolve_dm_user = AsyncMock(return_value="uid1")
        handler = AsyncMock(side_effect=RuntimeError("db error"))

        await handle_compact(msg, bus, resolver, compact_handler=handler)

        reply: OutboundMessage = bus.publish_outbound.call_args[0][0]
        assert "failed" in reply.content.lower()

    @pytest.mark.asyncio
    async def test_focus_topic_passed_to_handler(self) -> None:
        """Verify focus_topic is forwarded to compact_handler."""
        msg = _make_msg(is_group=False)
        bus = _mock_bus()
        resolver = MagicMock()
        resolver.resolve_dm_user = AsyncMock(return_value="uid1")

        result_obj = MagicMock()
        result_obj.compacted = True
        result_obj.message_count = 10
        result_obj.tokens_saved = 500
        handler = AsyncMock(return_value=result_obj)

        await handle_compact(msg, bus, resolver, compact_handler=handler, focus_topic="API design")

        handler.assert_called_once()
        _, kwargs = handler.call_args
        assert kwargs["focus_topic"] == "API design"

    @pytest.mark.asyncio
    async def test_focus_topic_shown_in_reply(self) -> None:
        """Verify focus_topic hint appears in success reply."""
        msg = _make_msg(is_group=False)
        bus = _mock_bus()
        resolver = MagicMock()
        resolver.resolve_dm_user = AsyncMock(return_value="uid1")

        result_obj = MagicMock()
        result_obj.compacted = True
        result_obj.message_count = 10
        result_obj.tokens_saved = 500
        handler = AsyncMock(return_value=result_obj)

        await handle_compact(msg, bus, resolver, compact_handler=handler, focus_topic="API design")

        reply: OutboundMessage = bus.publish_outbound.call_args[0][0]
        assert "API design" in reply.content

    @pytest.mark.asyncio
    async def test_focus_topic_truncated(self) -> None:
        """Verify long focus_topic is truncated to MAX_FOCUS_TOPIC_LENGTH."""
        from app.channels.protocols.compact import (
            MAX_FOCUS_TOPIC_LENGTH,
        )

        msg = _make_msg(is_group=False)
        bus = _mock_bus()
        resolver = MagicMock()
        resolver.resolve_dm_user = AsyncMock(return_value="uid1")

        result_obj = MagicMock()
        result_obj.compacted = True
        result_obj.message_count = 5
        result_obj.tokens_saved = 100
        handler = AsyncMock(return_value=result_obj)

        long_topic = "x" * 300
        await handle_compact(msg, bus, resolver, compact_handler=handler, focus_topic=long_topic)

        _, kwargs = handler.call_args
        assert len(kwargs["focus_topic"]) == MAX_FOCUS_TOPIC_LENGTH

    @pytest.mark.asyncio
    async def test_empty_focus_topic_no_hint(self) -> None:
        """Verify no topic hint when focus_topic is empty."""
        msg = _make_msg(is_group=False)
        bus = _mock_bus()
        resolver = MagicMock()
        resolver.resolve_dm_user = AsyncMock(return_value="uid1")

        result_obj = MagicMock()
        result_obj.compacted = True
        result_obj.message_count = 10
        result_obj.tokens_saved = 500
        handler = AsyncMock(return_value=result_obj)

        await handle_compact(msg, bus, resolver, compact_handler=handler, focus_topic="")

        reply: OutboundMessage = bus.publish_outbound.call_args[0][0]
        assert "(focus:" not in reply.content


class TestHandleTopicCommand:
    @pytest.mark.asyncio
    async def test_no_topic_resolver_no_thread(self) -> None:
        msg = _make_msg(thread_id=None)
        cmd = TopicCommand(action="bind")
        bus = _mock_bus()

        await handle_topic_command(msg, cmd, bus, topic_resolver=None)

        reply: OutboundMessage = bus.publish_outbound.call_args[0][0]
        assert "not configured" in reply.content.lower()

    @pytest.mark.asyncio
    async def test_no_topic_resolver(self) -> None:
        msg = _make_msg(thread_id="t1")
        cmd = TopicCommand(action="bind")
        bus = _mock_bus()

        await handle_topic_command(msg, cmd, bus, topic_resolver=None)

        reply: OutboundMessage = bus.publish_outbound.call_args[0][0]
        assert "not configured" in reply.content.lower()

    @pytest.mark.asyncio
    async def test_bind_success(self) -> None:
        msg = _make_msg(thread_id="t1", chat_id="c1")
        cmd = TopicCommand(action="bind", agent_id="my-agent")
        bus = _mock_bus()

        topic_resolver = MagicMock()
        ctx = MagicMock()
        ctx.agent_id = "my-agent"
        topic_resolver.bind_topic = AsyncMock(return_value=ctx)

        channel_obj = MagicMock()
        channel_obj.send_placeholder = AsyncMock(return_value="msg123")
        channel_obj.pin_message = AsyncMock()
        bus.get_channel = MagicMock(return_value=channel_obj)

        await handle_topic_command(msg, cmd, bus, topic_resolver=topic_resolver)

        topic_resolver.bind_topic.assert_called_once()
        channel_obj.pin_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_bind_no_pin_msg(self) -> None:
        msg = _make_msg(thread_id="t1", chat_id="c1")
        cmd = TopicCommand(action="bind")
        bus = _mock_bus()

        topic_resolver = MagicMock()
        ctx = MagicMock()
        ctx.agent_id = None
        topic_resolver.bind_topic = AsyncMock(return_value=ctx)

        channel_obj = MagicMock()
        channel_obj.send_placeholder = AsyncMock(return_value=None)
        bus.get_channel = MagicMock(return_value=channel_obj)

        await handle_topic_command(msg, cmd, bus, topic_resolver=topic_resolver)

        bus.publish_outbound.assert_called_once()

    @pytest.mark.asyncio
    async def test_unbind_success(self) -> None:
        msg = _make_msg(thread_id="t1", chat_id="c1")
        cmd = TopicCommand(action="unbind")
        bus = _mock_bus()

        topic_resolver = MagicMock()
        topic_resolver.unbind_topic = AsyncMock(return_value=True)

        await handle_topic_command(msg, cmd, bus, topic_resolver=topic_resolver)

        reply: OutboundMessage = bus.publish_outbound.call_args[0][0]
        assert "unbound" in reply.content.lower()

    @pytest.mark.asyncio
    async def test_unbind_not_found(self) -> None:
        msg = _make_msg(thread_id="t1", chat_id="c1")
        cmd = TopicCommand(action="unbind")
        bus = _mock_bus()

        topic_resolver = MagicMock()
        topic_resolver.unbind_topic = AsyncMock(return_value=False)

        await handle_topic_command(msg, cmd, bus, topic_resolver=topic_resolver)

        reply: OutboundMessage = bus.publish_outbound.call_args[0][0]
        assert "no binding" in reply.content.lower()

    @pytest.mark.asyncio
    async def test_topic_status_bound(self) -> None:
        msg = _make_msg(thread_id="t1", chat_id="c1")
        cmd = TopicCommand(action="topic")
        bus = _mock_bus()

        topic_resolver = MagicMock()
        topic_ctx = MagicMock()
        topic_ctx.agent_id = "agent1"
        topic_ctx.bound_at = "2025-01-01"
        topic_ctx.enabled = True
        topic_resolver.resolve_topic = AsyncMock(return_value=topic_ctx)

        await handle_topic_command(msg, cmd, bus, topic_resolver=topic_resolver)

        reply: OutboundMessage = bus.publish_outbound.call_args[0][0]
        assert "agent1" in reply.content

    @pytest.mark.asyncio
    async def test_topic_status_no_binding(self) -> None:
        msg = _make_msg(thread_id="t1", chat_id="c1")
        cmd = TopicCommand(action="topic")
        bus = _mock_bus()

        topic_resolver = MagicMock()
        topic_resolver.resolve_topic = AsyncMock(return_value=None)

        await handle_topic_command(msg, cmd, bus, topic_resolver=topic_resolver)

        reply: OutboundMessage = bus.publish_outbound.call_args[0][0]
        assert "defaults" in reply.content.lower()

    @pytest.mark.asyncio
    async def test_topic_exception(self) -> None:
        msg = _make_msg(thread_id="t1", chat_id="c1")
        cmd = TopicCommand(action="bind")
        bus = _mock_bus()

        topic_resolver = MagicMock()
        topic_resolver.bind_topic = AsyncMock(side_effect=RuntimeError("db error"))

        await handle_topic_command(msg, cmd, bus, topic_resolver=topic_resolver)

        bus.publish_outbound.assert_called_once()

    @pytest.mark.asyncio
    async def test_channel_level_bind(self) -> None:
        """Channel-level bind when thread_id is None."""
        msg = _make_msg(thread_id=None, chat_id="c1")
        cmd = TopicCommand(action="bind", agent_id="support-agent")
        bus = _mock_bus()

        topic_resolver = MagicMock()
        ctx = MagicMock()
        ctx.agent_id = "support-agent"
        topic_resolver.bind_topic = AsyncMock(return_value=ctx)

        channel_obj = MagicMock()
        channel_obj.send_placeholder = AsyncMock(return_value=None)
        bus.get_channel = MagicMock(return_value=channel_obj)

        await handle_topic_command(msg, cmd, bus, topic_resolver=topic_resolver)

        topic_resolver.bind_topic.assert_called_once_with("test", "c1", None, agent_id="support-agent")
        reply: OutboundMessage = bus.publish_outbound.call_args[0][0]
        assert "channel" in reply.content.lower()
        assert "support-agent" in reply.content

    @pytest.mark.asyncio
    async def test_channel_level_unbind(self) -> None:
        """Channel-level unbind when thread_id is None."""
        msg = _make_msg(thread_id=None, chat_id="c1")
        cmd = TopicCommand(action="unbind")
        bus = _mock_bus()

        topic_resolver = MagicMock()
        topic_resolver.unbind_topic = AsyncMock(return_value=True)

        await handle_topic_command(msg, cmd, bus, topic_resolver=topic_resolver)

        topic_resolver.unbind_topic.assert_called_once_with("test", "c1", None)
        reply: OutboundMessage = bus.publish_outbound.call_args[0][0]
        assert "channel" in reply.content.lower()
        assert "unbound" in reply.content.lower()

    @pytest.mark.asyncio
    async def test_channel_level_topic_status(self) -> None:
        """Channel-level /topic query when thread_id is None."""
        msg = _make_msg(thread_id=None, chat_id="c1")
        cmd = TopicCommand(action="topic")
        bus = _mock_bus()

        topic_resolver = MagicMock()
        topic_resolver.resolve_topic = AsyncMock(return_value=None)

        await handle_topic_command(msg, cmd, bus, topic_resolver=topic_resolver)

        topic_resolver.resolve_topic.assert_called_once_with("test", "c1", None)
        reply: OutboundMessage = bus.publish_outbound.call_args[0][0]
        assert "channel" in reply.content.lower()
        assert "defaults" in reply.content.lower()


class TestRegistryValidation:
    """Tests for CommandRegistry.register() validation and conflict detection."""

    def test_empty_name_raises(self) -> None:
        registry = CommandRegistry()
        with pytest.raises(ValueError, match="non-empty"):
            registry.register(CommandDef(name="", description="bad"))

    def test_name_with_spaces_raises(self) -> None:
        registry = CommandRegistry()
        with pytest.raises(ValueError, match="without spaces"):
            registry.register(CommandDef(name="my cmd", description="bad"))

    def test_name_with_leading_slash_raises(self) -> None:
        registry = CommandRegistry()
        with pytest.raises(ValueError, match="leading '/'"):
            registry.register(CommandDef(name="/test", description="bad"))

    def test_overwrite_system_command_raises(self) -> None:
        registry = CommandRegistry()
        with pytest.raises(ValueError, match="Cannot overwrite system command"):
            registry.register(
                CommandDef(
                    name="stop",
                    description="hijack",
                    kind=CommandKind.SKILL,
                    skill_ids=["x"],
                )
            )

    def test_overwrite_system_alias_raises(self) -> None:
        registry = CommandRegistry()
        system_cmd = CommandDef(name="mycmd", description="safe", kind=CommandKind.SYSTEM, aliases=("mc",))
        registry.register(system_cmd)
        with pytest.raises(ValueError, match="Cannot overwrite system command alias"):
            registry.register(
                CommandDef(
                    name="another",
                    description="hijack",
                    aliases=("mc",),
                    kind=CommandKind.AGENT_ROUTE,
                )
            )

    def test_overwrite_non_system_logs_warning(self) -> None:
        registry = CommandRegistry()
        cmd1 = CommandDef(
            name="custom",
            description="first",
            kind=CommandKind.AGENT_ROUTE,
            agent_id="a1",
        )
        cmd2 = CommandDef(
            name="custom",
            description="second",
            kind=CommandKind.AGENT_ROUTE,
            agent_id="a2",
        )
        registry.register(cmd1)
        registry.register(cmd2)
        resolved = registry.resolve("/custom")
        assert resolved is not None
        assert resolved.command_def.agent_id == "a2"

    def test_invalid_alias_raises(self) -> None:
        registry = CommandRegistry()
        with pytest.raises(ValueError, match="Invalid alias"):
            registry.register(CommandDef(name="good", description="ok", aliases=("bad alias",)))


class TestRegistryEdgeCases:
    """Tests for edge cases in CommandRegistry.resolve()."""

    def test_resolve_bare_slash_returns_none(self) -> None:
        registry = CommandRegistry()
        assert registry.resolve("/") is None

    def test_resolve_args_on_non_parse_args_cmd_returns_none(self) -> None:
        registry = CommandRegistry()
        resolved = registry.resolve("/stop extra args")
        assert resolved is None

    def test_all_commands_returns_list(self) -> None:
        registry = CommandRegistry()
        cmds = registry.all_commands()
        assert isinstance(cmds, list)
        assert len(cmds) > 0

    def test_help_lines_with_alias(self) -> None:
        registry = CommandRegistry()
        cmd = CommandDef(
            name="report",
            description="Generate report",
            kind=CommandKind.SKILL,
            skill_ids=("s1",),
            aliases=("rpt",),
            category="Skill",
        )
        registry.register(cmd)
        text = "\n".join(registry.help_lines())
        assert "alias" in text
        assert "/rpt" in text


class TestRegistryUnregisterAndFilter:
    """Tests for CommandRegistry.unregister() and commands_by_kind()."""

    def test_unregister_existing(self) -> None:
        registry = CommandRegistry()
        cmd = CommandDef(name="custom", description="test", kind=CommandKind.SKILL, skill_ids=("s1",))
        registry.register(cmd)
        assert registry.unregister("custom") is True
        assert registry.get("custom") is None

    def test_unregister_removes_aliases(self) -> None:
        registry = CommandRegistry()
        cmd = CommandDef(
            name="report",
            description="test",
            kind=CommandKind.SKILL,
            skill_ids=("s1",),
            aliases=("rpt", "rp"),
        )
        registry.register(cmd)
        registry.unregister("report")
        assert registry.get("rpt") is None
        assert registry.get("rp") is None

    def test_unregister_nonexistent(self) -> None:
        registry = CommandRegistry()
        assert registry.unregister("nonexistent") is False

    def test_commands_by_kind_system(self) -> None:
        registry = CommandRegistry()
        system_cmds = registry.commands_by_kind(CommandKind.SYSTEM)
        assert len(system_cmds) > 0
        assert all(c.kind == CommandKind.SYSTEM for c in system_cmds)

    def test_commands_by_kind_skill(self) -> None:
        registry = CommandRegistry()
        cmd = CommandDef(name="daily", description="test", kind=CommandKind.SKILL, skill_ids=("s1",))
        registry.register(cmd)
        skill_cmds = registry.commands_by_kind(CommandKind.SKILL)
        assert len(skill_cmds) == 1
        assert skill_cmds[0].name == "daily"

    def test_commands_by_kind_empty(self) -> None:
        registry = CommandRegistry()
        assert len(registry.commands_by_kind(CommandKind.SKILL)) == 0

    def test_help_lines_includes_skill_commands(self) -> None:
        registry = CommandRegistry()
        cmd = CommandDef(
            name="daily",
            description="Daily report",
            kind=CommandKind.SKILL,
            skill_ids=("s1",),
            category="Skill",
        )
        registry.register(cmd)
        lines = registry.help_lines()
        help_text = "\n".join(lines)
        assert "/daily" in help_text
        assert "Daily report" in help_text


class TestSkillCommandRegistration:
    """Tests for SKILL command registration, resolution, and robustness."""

    def test_skill_command_resolve(self) -> None:
        registry = CommandRegistry()
        cmd = CommandDef(
            name="daily-report",
            description="Generate daily report",
            kind=CommandKind.SKILL,
            skill_ids=("daily_report_skill",),
            aliases=("dr",),
            parse_args=True,
            category="Skill",
        )
        registry.register(cmd)
        resolved = registry.resolve("/daily-report some args")
        assert resolved is not None
        assert resolved.command_def.kind == CommandKind.SKILL
        assert resolved.command_def.skill_ids == ("daily_report_skill",)
        assert resolved.raw_args == "some args"

    def test_skill_command_resolve_via_alias(self) -> None:
        registry = CommandRegistry()
        cmd = CommandDef(
            name="daily-report",
            description="test",
            kind=CommandKind.SKILL,
            skill_ids=("s1",),
            aliases=("dr",),
            parse_args=True,
        )
        registry.register(cmd)
        resolved = registry.resolve("/dr hello")
        assert resolved is not None
        assert resolved.command_def.name == "daily-report"
        assert resolved.raw_args == "hello"

    def test_skill_command_no_args(self) -> None:
        registry = CommandRegistry()
        cmd = CommandDef(
            name="daily-report",
            description="test",
            kind=CommandKind.SKILL,
            skill_ids=("s1",),
            parse_args=True,
        )
        registry.register(cmd)
        resolved = registry.resolve("/daily-report")
        assert resolved is not None
        assert resolved.raw_args == ""

    def test_register_skill_with_system_name_raises(self) -> None:
        registry = CommandRegistry()
        with pytest.raises(ValueError, match="Cannot overwrite system command"):
            registry.register(CommandDef(name="stop", description="bad", kind=CommandKind.SKILL, skill_ids=["x"]))


class TestUpdateSkillCommands:
    """Tests for ChannelGateway.update_skill_commands() runtime hot-reload."""

    def _make_gateway_with_registry(self) -> tuple:
        """Create a minimal gateway with router containing a CommandRegistry."""
        from app.channels.core.gateway import ChannelGateway

        gw = ChannelGateway()
        mock_router = MagicMock()
        mock_router._registry = CommandRegistry()
        gw._router = mock_router
        return gw, mock_router._registry

    def test_add_skill_commands(self) -> None:
        gw, registry = self._make_gateway_with_registry()
        cmds = (
            CommandDef(name="report", description="test", kind=CommandKind.SKILL, skill_ids=("s1",)),
            CommandDef(
                name="analyze",
                description="test",
                kind=CommandKind.SKILL,
                skill_ids=("s2",),
            ),
        )
        gw.update_skill_commands(cmds)
        assert len(registry.commands_by_kind(CommandKind.SKILL)) == 2
        assert registry.get("report") is not None
        assert registry.get("analyze") is not None

    def test_replace_skill_commands(self) -> None:
        gw, registry = self._make_gateway_with_registry()
        old_cmds = (CommandDef(name="old-cmd", description="old", kind=CommandKind.SKILL, skill_ids=("s1",)),)
        gw.update_skill_commands(old_cmds)
        assert registry.get("old-cmd") is not None

        new_cmds = (CommandDef(name="new-cmd", description="new", kind=CommandKind.SKILL, skill_ids=("s2",)),)
        gw.update_skill_commands(new_cmds)
        assert registry.get("old-cmd") is None
        assert registry.get("new-cmd") is not None
        assert len(registry.commands_by_kind(CommandKind.SKILL)) == 1

    def test_clear_all_skill_commands(self) -> None:
        gw, registry = self._make_gateway_with_registry()
        cmds = (CommandDef(name="cmd1", description="test", kind=CommandKind.SKILL, skill_ids=("s1",)),)
        gw.update_skill_commands(cmds)
        assert len(registry.commands_by_kind(CommandKind.SKILL)) == 1

        gw.update_skill_commands(())
        assert len(registry.commands_by_kind(CommandKind.SKILL)) == 0

    def test_system_commands_preserved(self) -> None:
        gw, registry = self._make_gateway_with_registry()
        system_count_before = len(registry.commands_by_kind(CommandKind.SYSTEM))
        cmds = (CommandDef(name="report", description="test", kind=CommandKind.SKILL, skill_ids=("s1",)),)
        gw.update_skill_commands(cmds)
        system_count_after = len(registry.commands_by_kind(CommandKind.SYSTEM))
        assert system_count_before == system_count_after

    def test_invalid_command_skipped_others_registered(self) -> None:
        """One invalid command (system name conflict) should not prevent others."""
        gw, registry = self._make_gateway_with_registry()
        cmds = (
            CommandDef(
                name="valid-cmd",
                description="ok",
                kind=CommandKind.SKILL,
                skill_ids=("s1",),
            ),
            CommandDef(name="stop", description="bad", kind=CommandKind.SKILL, skill_ids=("s2",)),
            CommandDef(
                name="another-valid",
                description="ok",
                kind=CommandKind.SKILL,
                skill_ids=("s3",),
            ),
        )
        gw.update_skill_commands(cmds)
        assert registry.get("valid-cmd") is not None
        assert registry.get("another-valid") is not None
        assert registry.resolve("/stop").command_def.kind == CommandKind.SYSTEM

    def test_no_router_is_noop(self) -> None:
        from app.channels.core.gateway import ChannelGateway

        gw = ChannelGateway()
        cmds = (CommandDef(name="cmd", description="test", kind=CommandKind.SKILL, skill_ids=("s1",)),)
        gw.update_skill_commands(cmds)  # should not raise
