"""Integration tests for /learn command — full routing dispatch with real handler.

Covers: CommandRegistry resolution, RouterCommandsMixin._handle_learn_command
dispatch, ChannelLearnCommandHandler prompt construction, and all edge cases.
No LLM calls — validates the complete path from user input to agent submission.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.channels.routing.command_defs import CommandAction, CommandKind
from app.channels.routing.command_registry import CommandRegistry
from app.channels.types.messages import InboundMessage, OutboundMessage
from app.core.channel_bridge.learn_handler import ChannelLearnCommandHandler


def _make_msg(
    content: str = "/learn",
    *,
    channel: str = "test",
    sender_id: str = "u1",
    chat_id: str = "chat_1",
    is_group: bool = False,
    thread_id: str | None = None,
    message_id: str | None = None,
) -> InboundMessage:
    return InboundMessage(
        channel=channel,
        sender_id=sender_id,
        chat_id=chat_id,
        content=content,
        is_group=is_group,
        thread_id=thread_id,
        message_id=message_id,
        metadata={"message_id": message_id or ""},
    )


# ── CommandRegistry integration ──────────────────────────────────────────


class TestLearnCommandRegistry:
    """Verify /learn is properly registered and resolvable."""

    @pytest.fixture
    def registry(self) -> CommandRegistry:
        return CommandRegistry()

    def test_learn_registered(self, registry: CommandRegistry) -> None:
        cmd = registry.get("learn")
        assert cmd is not None
        assert cmd.action == CommandAction.LEARN
        assert cmd.kind == CommandKind.SYSTEM
        assert cmd.category == "Skills"

    def test_resolve_learn_with_url(self, registry: CommandRegistry) -> None:
        result = registry.resolve("/learn https://docs.example.com/api")
        assert result is not None
        assert result.command_def.action == CommandAction.LEARN
        assert result.raw_args == "https://docs.example.com/api"

    def test_resolve_learn_with_path(self, registry: CommandRegistry) -> None:
        result = registry.resolve("/learn ./scripts/deploy.sh")
        assert result is not None
        assert result.raw_args == "./scripts/deploy.sh"

    def test_resolve_learn_with_text(self, registry: CommandRegistry) -> None:
        result = registry.resolve("/learn the deployment workflow we just did")
        assert result is not None
        assert result.raw_args == "the deployment workflow we just did"

    def test_resolve_learn_empty_args(self, registry: CommandRegistry) -> None:
        result = registry.resolve("/learn")
        assert result is not None
        assert result.raw_args == ""

    def test_resolve_learn_case_insensitive(self, registry: CommandRegistry) -> None:
        result = registry.resolve("/Learn https://example.com")
        assert result is not None
        assert result.command_def.action == CommandAction.LEARN

    def test_learn_in_help_output(self, registry: CommandRegistry) -> None:
        lines = registry.help_lines()
        combined = "\n".join(lines)
        assert "/learn" in combined

    def test_learn_parse_args_enabled(self, registry: CommandRegistry) -> None:
        cmd = registry.get("learn")
        assert cmd is not None
        assert cmd.parse_args is True
        assert cmd.args_pattern is not None


# ── RouterCommandsMixin._handle_learn_command integration ────────────────


class _FakeRouterHost:
    """Minimal stub implementing RouterCommandsHost protocol for _handle_learn_command."""

    def __init__(
        self,
        learn_handler: ChannelLearnCommandHandler | None = None,
    ) -> None:
        self._learn_handler = learn_handler
        self._bus = MagicMock()
        self._bus.publish_outbound = AsyncMock()
        self._gate = MagicMock()
        self._gate.submit = MagicMock()

    @property
    def outbound_messages(self) -> list[OutboundMessage]:
        return [call.args[0] for call in self._bus.publish_outbound.call_args_list]

    @property
    def submitted_messages(self) -> list[InboundMessage]:
        return [call.args[0] for call in self._gate.submit.call_args_list]


async def _dispatch_learn(
    host: _FakeRouterHost,
    msg: InboundMessage,
    raw_args: str,
) -> None:
    """Execute _handle_learn_command on the fake host using real mixin logic."""
    from app.channels.routing.router_commands import RouterCommandsMixin

    bound = RouterCommandsMixin._handle_learn_command.__get__(host, type(host))
    await bound(msg, raw_args)


class TestLearnCommandDispatch:
    """Integration: _handle_learn_command with real ChannelLearnCommandHandler."""

    @pytest.fixture
    def handler(self) -> ChannelLearnCommandHandler:
        return ChannelLearnCommandHandler()

    @pytest.fixture
    def host(self, handler: ChannelLearnCommandHandler) -> _FakeRouterHost:
        return _FakeRouterHost(learn_handler=handler)

    @pytest.mark.asyncio
    async def test_url_submitted_to_gate(self, host: _FakeRouterHost) -> None:
        msg = _make_msg("/learn https://docs.stripe.com/webhooks")
        await _dispatch_learn(host, msg, "https://docs.stripe.com/webhooks")

        assert host._gate.submit.call_count == 1
        submitted = host.submitted_messages[0]
        assert "[/learn]" in submitted.content
        assert "web_search_tool" in submitted.content
        assert "https://docs.stripe.com/webhooks" in submitted.content

    @pytest.mark.asyncio
    async def test_path_submitted_to_gate(self, host: _FakeRouterHost) -> None:
        msg = _make_msg("/learn ./scripts/deploy.sh")
        await _dispatch_learn(host, msg, "./scripts/deploy.sh")

        submitted = host.submitted_messages[0]
        assert "file_read_tool" in submitted.content
        assert "./scripts/deploy.sh" in submitted.content

    @pytest.mark.asyncio
    async def test_text_submitted_to_gate(self, host: _FakeRouterHost) -> None:
        msg = _make_msg("/learn the k8s deployment workflow")
        await _dispatch_learn(host, msg, "the k8s deployment workflow")

        submitted = host.submitted_messages[0]
        assert "the k8s deployment workflow" in submitted.content

    @pytest.mark.asyncio
    async def test_empty_args_fallback(self, host: _FakeRouterHost) -> None:
        msg = _make_msg("/learn")
        await _dispatch_learn(host, msg, "")

        assert host._gate.submit.call_count == 1
        submitted = host.submitted_messages[0]
        assert "conversation" in submitted.content.lower()

    @pytest.mark.asyncio
    async def test_whitespace_only_args_fallback(self, host: _FakeRouterHost) -> None:
        msg = _make_msg("/learn   ")
        await _dispatch_learn(host, msg, "   ")

        submitted = host.submitted_messages[0]
        assert "conversation" in submitted.content.lower()

    @pytest.mark.asyncio
    async def test_no_handler_sends_not_configured(self) -> None:
        host = _FakeRouterHost(learn_handler=None)
        msg = _make_msg("/learn https://example.com")
        await _dispatch_learn(host, msg, "https://example.com")

        assert host._gate.submit.call_count == 0
        assert host._bus.publish_outbound.call_count == 1
        reply = host.outbound_messages[0]
        assert reply.recipient_id == "chat_1"

    @pytest.mark.asyncio
    async def test_preserves_channel_and_sender(self, host: _FakeRouterHost) -> None:
        msg = _make_msg(
            "/learn https://example.com",
            channel="telegram",
            sender_id="tg_user_42",
            chat_id="tg_chat_99",
        )
        await _dispatch_learn(host, msg, "https://example.com")

        submitted = host.submitted_messages[0]
        assert submitted.channel == "telegram"
        assert submitted.sender_id == "tg_user_42"

    @pytest.mark.asyncio
    async def test_preserves_thread_id(self, host: _FakeRouterHost) -> None:
        msg = _make_msg(
            "/learn https://example.com",
            thread_id="thread_42",
            is_group=True,
            message_id="msg_99",
        )
        await _dispatch_learn(host, msg, "https://example.com")

        submitted = host.submitted_messages[0]
        assert submitted.thread_id == "thread_42"

    @pytest.mark.asyncio
    async def test_prompt_contains_skill_manage_tool(self, host: _FakeRouterHost) -> None:
        msg = _make_msg("/learn anything")
        await _dispatch_learn(host, msg, "anything")

        submitted = host.submitted_messages[0]
        assert "skill_manage_tool" in submitted.content
        assert 'action="save"' in submitted.content

    @pytest.mark.asyncio
    async def test_prompt_contains_authoring_standards(self, host: _FakeRouterHost) -> None:
        msg = _make_msg("/learn anything")
        await _dispatch_learn(host, msg, "anything")

        submitted = host.submitted_messages[0]
        assert "## When to Use" in submitted.content
        assert "## Verification" in submitted.content

    @pytest.mark.asyncio
    async def test_no_wrong_tool_names_in_submitted(self, host: _FakeRouterHost) -> None:
        msg = _make_msg("/learn https://example.com")
        await _dispatch_learn(host, msg, "https://example.com")

        content = host.submitted_messages[0].content
        assert "`web_search`" not in content or "web_search_tool" in content
        assert "`read_file`" not in content
        assert "`search_files`" not in content

    @pytest.mark.asyncio
    async def test_never_returns_none_for_any_input(self, host: _FakeRouterHost) -> None:
        for args in ["", "   ", "https://x.com", "./f.py", "~/f.md", "/abs", "free text"]:
            host._gate.submit.reset_mock()
            host._bus.publish_outbound.reset_mock()
            msg = _make_msg(f"/learn {args}")
            await _dispatch_learn(host, msg, args)
            assert host._gate.submit.call_count == 1, f"Should submit for args={args!r}"
            assert host._bus.publish_outbound.call_count == 0, f"Should not error for args={args!r}"


# ── Edge case scenarios ──────────────────────────────────────────────────


class TestLearnCommandEdgeCases:
    """Edge cases: unicode, special chars, long input, group messages."""

    @pytest.fixture
    def handler(self) -> ChannelLearnCommandHandler:
        return ChannelLearnCommandHandler()

    @pytest.fixture
    def host(self, handler: ChannelLearnCommandHandler) -> _FakeRouterHost:
        return _FakeRouterHost(learn_handler=handler)

    @pytest.mark.asyncio
    async def test_unicode_url(self, host: _FakeRouterHost) -> None:
        url = "https://example.com/路径/文档"
        msg = _make_msg(f"/learn {url}")
        await _dispatch_learn(host, msg, url)
        submitted = host.submitted_messages[0]
        assert url in submitted.content

    @pytest.mark.asyncio
    async def test_unicode_free_text(self, host: _FakeRouterHost) -> None:
        text = "部署K8s集群的工作流程"
        msg = _make_msg(f"/learn {text}")
        await _dispatch_learn(host, msg, text)
        submitted = host.submitted_messages[0]
        assert text in submitted.content

    @pytest.mark.asyncio
    async def test_url_with_query_and_fragment(self, host: _FakeRouterHost) -> None:
        url = "https://docs.example.com/api?v=2&lang=en#auth"
        msg = _make_msg(f"/learn {url}")
        await _dispatch_learn(host, msg, url)
        submitted = host.submitted_messages[0]
        assert url in submitted.content
        assert "INPUT TYPE: url" in submitted.content

    @pytest.mark.asyncio
    async def test_long_free_text_input(self, host: _FakeRouterHost) -> None:
        long_text = "deploy " * 500
        msg = _make_msg(f"/learn {long_text}")
        await _dispatch_learn(host, msg, long_text)
        assert host._gate.submit.call_count == 1

    @pytest.mark.asyncio
    async def test_tab_only_args_triggers_fallback(self, host: _FakeRouterHost) -> None:
        msg = _make_msg("/learn\t\t")
        await _dispatch_learn(host, msg, "\t\t")
        submitted = host.submitted_messages[0]
        assert "conversation" in submitted.content.lower()

    @pytest.mark.asyncio
    async def test_group_message_no_reply_to_id(self, host: _FakeRouterHost) -> None:
        """In non-group context, reply_to_id should not be set on error."""
        host_no_handler = _FakeRouterHost(learn_handler=None)
        msg = _make_msg("/learn x", is_group=False)
        await _dispatch_learn(host_no_handler, msg, "x")
        reply = host_no_handler.outbound_messages[0]
        assert reply.reply_to_id is None

    @pytest.mark.asyncio
    async def test_group_message_has_reply_to_id(self, host: _FakeRouterHost) -> None:
        """In group context, error reply should reference the original message."""
        host_no_handler = _FakeRouterHost(learn_handler=None)
        msg = _make_msg(
            "/learn x", is_group=True, message_id="msg_42",
        )
        await _dispatch_learn(host_no_handler, msg, "x")
        reply = host_no_handler.outbound_messages[0]
        assert reply.reply_to_id == "msg_42"

    @pytest.mark.asyncio
    async def test_concurrent_calls_independent(self, host: _FakeRouterHost) -> None:
        """Multiple sequential calls should each produce independent results."""
        for _i, args in enumerate(["https://a.com", "./b.py", "text c"]):
            host._gate.submit.reset_mock()
            await _dispatch_learn(host, _make_msg(f"/learn {args}"), args)
            assert host._gate.submit.call_count == 1
            submitted = host.submitted_messages[-1]
            assert args in submitted.content

    @pytest.mark.asyncio
    async def test_path_with_backslash(self, host: _FakeRouterHost) -> None:
        path = "\\server\\share\\file.txt"
        msg = _make_msg(f"/learn {path}")
        await _dispatch_learn(host, msg, path)
        submitted = host.submitted_messages[0]
        assert path in submitted.content

    @pytest.mark.asyncio
    async def test_submitted_content_is_not_original(self, host: _FakeRouterHost) -> None:
        """The submitted message should have prompt content, not the raw /learn command."""
        msg = _make_msg("/learn https://example.com")
        await _dispatch_learn(host, msg, "https://example.com")
        submitted = host.submitted_messages[0]
        assert submitted.content != "/learn https://example.com"
        assert "[/learn]" in submitted.content
        assert len(submitted.content) > 100


class TestLearnCommandRegistryEdgeCases:
    """Edge-case resolution scenarios for the command registry."""

    @pytest.fixture
    def registry(self) -> CommandRegistry:
        return CommandRegistry()

    def test_resolve_with_leading_trailing_spaces(self, registry: CommandRegistry) -> None:
        result = registry.resolve("  /learn https://example.com  ")
        assert result is not None
        assert result.command_def.action == CommandAction.LEARN

    def test_resolve_learn_multiple_spaces_between(self, registry: CommandRegistry) -> None:
        result = registry.resolve("/learn   https://example.com")
        assert result is not None
        assert result.raw_args == "https://example.com"

    def test_unknown_command_returns_none(self, registry: CommandRegistry) -> None:
        result = registry.resolve("/notacommand something")
        assert result is None

    def test_learn_without_slash_returns_none(self, registry: CommandRegistry) -> None:
        result = registry.resolve("learn https://example.com")
        assert result is None

    def test_just_slash_returns_none(self, registry: CommandRegistry) -> None:
        result = registry.resolve("/")
        assert result is None
