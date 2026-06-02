"""Tests for /background (/btw /bg) slash command — command_defs, protocol, subcommand parsing, dispatch."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.channels.protocols.background_task import (
    BackgroundTaskHandler,
    BackgroundTaskInfo,
)
from app.channels.routing.command_defs import (
    SYSTEM_COMMANDS,
    CommandAction,
)
from app.channels.routing.command_registry import (
    CommandRegistry,
)
from app.channels.types import InboundMessage, OutboundMessage


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


# ── command_defs tests ─────────────────────────────────────────────────


class TestBackgroundCommandDef:
    """Tests for /background CommandDef registration."""

    def test_background_action_exists(self) -> None:
        assert hasattr(CommandAction, "BACKGROUND")

    def test_background_in_system_commands(self) -> None:
        bg_cmds = [c for c in SYSTEM_COMMANDS if c.action == CommandAction.BACKGROUND]
        assert len(bg_cmds) == 1

    def test_background_command_properties(self) -> None:
        bg_cmd = next(c for c in SYSTEM_COMMANDS if c.action == CommandAction.BACKGROUND)
        assert bg_cmd.name == "background"
        assert bg_cmd.parse_args is True
        assert "btw" in bg_cmd.aliases
        assert "bg" in bg_cmd.aliases

    def test_background_registered_in_registry(self) -> None:
        registry = CommandRegistry()
        result = registry.resolve("/background")
        assert result is not None
        assert result.command_def.action == CommandAction.BACKGROUND

    def test_btw_alias_resolves(self) -> None:
        registry = CommandRegistry()
        result = registry.resolve("/btw some task")
        assert result is not None
        assert result.command_def.action == CommandAction.BACKGROUND
        assert result.raw_args == "some task"

    def test_bg_alias_resolves(self) -> None:
        registry = CommandRegistry()
        result = registry.resolve("/bg do something")
        assert result is not None
        assert result.command_def.action == CommandAction.BACKGROUND
        assert result.raw_args == "do something"


# ── BackgroundTaskHandler Protocol tests ───────────────────────────────


class TestBackgroundTaskHandlerProtocol:
    """Tests for BackgroundTaskHandler protocol compliance."""

    def test_protocol_is_runtime_checkable(self) -> None:
        class MockHandler:
            async def spawn_background(self, msg: InboundMessage, prompt: str) -> str:
                return "bg_abc"

            async def cancel_background(self, msg: InboundMessage, task_id: str) -> bool:
                return True

            async def list_background(self, msg: InboundMessage) -> list[BackgroundTaskInfo]:
                return []

            async def steer_background(self, msg: InboundMessage, task_id: str, instruction: str) -> bool:
                return True

        handler = MockHandler()
        assert isinstance(handler, BackgroundTaskHandler)

    def test_non_handler_fails_check(self) -> None:
        class NotAHandler:
            pass

        assert not isinstance(NotAHandler(), BackgroundTaskHandler)

    def test_partial_handler_fails_check(self) -> None:
        class PartialHandler:
            async def spawn_background(self, msg: InboundMessage, prompt: str) -> str:
                return "bg_abc"

        assert not isinstance(PartialHandler(), BackgroundTaskHandler)


# ── BackgroundTaskInfo dataclass tests ─────────────────────────────────


class TestBackgroundTaskInfo:
    def test_frozen(self) -> None:
        info = BackgroundTaskInfo(
            task_id="bg_abc",
            prompt="test prompt",
            status="running",
            created_at=1000.0,
        )
        with pytest.raises(FrozenInstanceError):
            info.task_id = "changed"  # type: ignore[misc]

    def test_optional_fields(self) -> None:
        info = BackgroundTaskInfo(
            task_id="bg_abc",
            prompt="test",
            status="completed",
            created_at=1000.0,
            completed_at=2000.0,
            result_preview="Result...",
        )
        assert info.completed_at == 2000.0
        assert info.result_preview == "Result..."

    def test_defaults(self) -> None:
        info = BackgroundTaskInfo(
            task_id="bg_abc",
            prompt="test",
            status="running",
            created_at=1000.0,
        )
        assert info.completed_at is None
        assert info.result_preview is None


# ── _handle_background_command mixin tests ─────────────────────────────


class TestHandleBackgroundCommand:
    """Tests for _handle_background_command mixin method."""

    def _make_host(
        self,
        background_handler: BackgroundTaskHandler | None = None,
    ) -> MagicMock:
        host = MagicMock()
        host._background_handler = background_handler
        host._bus = MagicMock()
        host._bus.publish_outbound = AsyncMock()
        return host

    @pytest.mark.asyncio
    async def test_no_handler_returns_not_available(self) -> None:
        from app.channels.routing.router_commands import RouterCommandsMixin

        host = self._make_host(background_handler=None)
        msg = _make_msg()
        await RouterCommandsMixin._handle_background_command(host, msg, "some task")

        host._bus.publish_outbound.assert_called_once()
        reply: OutboundMessage = host._bus.publish_outbound.call_args[0][0]
        assert "not available" in reply.content.lower()

    @pytest.mark.asyncio
    async def test_empty_args_shows_usage(self) -> None:
        from app.channels.routing.router_commands import RouterCommandsMixin

        handler = MagicMock()
        host = self._make_host(background_handler=handler)
        msg = _make_msg()
        await RouterCommandsMixin._handle_background_command(host, msg, "")

        host._bus.publish_outbound.assert_called_once()
        reply: OutboundMessage = host._bus.publish_outbound.call_args[0][0]
        assert "usage" in reply.content.lower()

    @pytest.mark.asyncio
    async def test_list_empty(self) -> None:
        from app.channels.routing.router_commands import RouterCommandsMixin

        handler = MagicMock()
        handler.list_background = AsyncMock(return_value=[])
        host = self._make_host(background_handler=handler)
        msg = _make_msg()
        await RouterCommandsMixin._handle_background_command(host, msg, "list")

        reply: OutboundMessage = host._bus.publish_outbound.call_args[0][0]
        assert "no background tasks" in reply.content.lower()

    @pytest.mark.asyncio
    async def test_list_with_tasks(self) -> None:
        from app.channels.routing.router_commands import RouterCommandsMixin

        tasks = [
            BackgroundTaskInfo(
                task_id="bg_abc",
                prompt="research AI",
                status="running",
                created_at=1000.0,
            ),
            BackgroundTaskInfo(
                task_id="bg_def",
                prompt="generate report",
                status="completed",
                created_at=900.0,
                completed_at=1100.0,
                result_preview="Done",
            ),
        ]
        handler = MagicMock()
        handler.list_background = AsyncMock(return_value=tasks)
        host = self._make_host(background_handler=handler)
        msg = _make_msg()
        await RouterCommandsMixin._handle_background_command(host, msg, "list")

        reply: OutboundMessage = host._bus.publish_outbound.call_args[0][0]
        assert "bg_abc" in reply.content
        assert "bg_def" in reply.content
        assert "research AI" in reply.content

    @pytest.mark.asyncio
    async def test_cancel_success(self) -> None:
        from app.channels.routing.router_commands import RouterCommandsMixin

        handler = MagicMock()
        handler.cancel_background = AsyncMock(return_value=True)
        host = self._make_host(background_handler=handler)
        msg = _make_msg()
        await RouterCommandsMixin._handle_background_command(host, msg, "cancel bg_abc")

        reply: OutboundMessage = host._bus.publish_outbound.call_args[0][0]
        assert "bg_abc" in reply.content
        assert "cancelled" in reply.content.lower()

    @pytest.mark.asyncio
    async def test_cancel_not_found(self) -> None:
        from app.channels.routing.router_commands import RouterCommandsMixin

        handler = MagicMock()
        handler.cancel_background = AsyncMock(return_value=False)
        host = self._make_host(background_handler=handler)
        msg = _make_msg()
        await RouterCommandsMixin._handle_background_command(host, msg, "cancel bg_xyz")

        reply: OutboundMessage = host._bus.publish_outbound.call_args[0][0]
        assert "not found" in reply.content.lower()

    @pytest.mark.asyncio
    async def test_cancel_bare_word_is_treated_as_spawn(self) -> None:
        """'/btw cancel' (no task_id) is treated as spawn with prompt='cancel'."""
        from app.channels.routing.router_commands import RouterCommandsMixin

        handler = MagicMock()
        handler.spawn_background = AsyncMock(return_value="bg_cancel1")
        host = self._make_host(background_handler=handler)
        msg = _make_msg()
        await RouterCommandsMixin._handle_background_command(host, msg, "cancel")

        handler.spawn_background.assert_called_once_with(msg, "cancel")
        reply: OutboundMessage = host._bus.publish_outbound.call_args[0][0]
        assert "bg_cancel1" in reply.content

    @pytest.mark.asyncio
    async def test_steer_success(self) -> None:
        from app.channels.routing.router_commands import RouterCommandsMixin

        handler = MagicMock()
        handler.steer_background = AsyncMock(return_value=True)
        host = self._make_host(background_handler=handler)
        msg = _make_msg()
        await RouterCommandsMixin._handle_background_command(host, msg, "steer bg_abc focus on APIs")

        reply: OutboundMessage = host._bus.publish_outbound.call_args[0][0]
        assert "bg_abc" in reply.content
        assert "steering" in reply.content.lower()
        handler.steer_background.assert_called_once_with(msg, "bg_abc", "focus on APIs")

    @pytest.mark.asyncio
    async def test_steer_not_found(self) -> None:
        from app.channels.routing.router_commands import RouterCommandsMixin

        handler = MagicMock()
        handler.steer_background = AsyncMock(return_value=False)
        host = self._make_host(background_handler=handler)
        msg = _make_msg()
        await RouterCommandsMixin._handle_background_command(host, msg, "steer bg_xyz do stuff")

        reply: OutboundMessage = host._bus.publish_outbound.call_args[0][0]
        assert "not found" in reply.content.lower()

    @pytest.mark.asyncio
    async def test_steer_missing_instruction(self) -> None:
        from app.channels.routing.router_commands import RouterCommandsMixin

        handler = MagicMock()
        host = self._make_host(background_handler=handler)
        msg = _make_msg()
        await RouterCommandsMixin._handle_background_command(host, msg, "steer bg_abc")

        reply: OutboundMessage = host._bus.publish_outbound.call_args[0][0]
        assert "usage" in reply.content.lower()

    @pytest.mark.asyncio
    async def test_spawn_success(self) -> None:
        from app.channels.routing.router_commands import RouterCommandsMixin

        handler = MagicMock()
        handler.spawn_background = AsyncMock(return_value="bg_new123")
        host = self._make_host(background_handler=handler)
        msg = _make_msg()
        await RouterCommandsMixin._handle_background_command(host, msg, "research quantum computing")

        reply: OutboundMessage = host._bus.publish_outbound.call_args[0][0]
        assert "bg_new123" in reply.content
        assert "started" in reply.content.lower()
        handler.spawn_background.assert_called_once_with(msg, "research quantum computing")

    @pytest.mark.asyncio
    async def test_spawn_concurrent_limit(self) -> None:
        from app.channels.routing.router_commands import RouterCommandsMixin

        handler = MagicMock()
        handler.spawn_background = AsyncMock(
            side_effect=RuntimeError("Maximum concurrent background tasks reached (5).")
        )
        host = self._make_host(background_handler=handler)
        msg = _make_msg()
        await RouterCommandsMixin._handle_background_command(host, msg, "another task")

        reply: OutboundMessage = host._bus.publish_outbound.call_args[0][0]
        assert "maximum" in reply.content.lower()

    @pytest.mark.asyncio
    async def test_reply_uses_correct_recipient(self) -> None:
        from app.channels.routing.router_commands import RouterCommandsMixin

        handler = MagicMock()
        handler.list_background = AsyncMock(return_value=[])
        host = self._make_host(background_handler=handler)
        msg = _make_msg(channel="telegram", chat_id="group42", sender_id="user1")
        await RouterCommandsMixin._handle_background_command(host, msg, "list")

        reply: OutboundMessage = host._bus.publish_outbound.call_args[0][0]
        assert reply.channel == "telegram"
        assert reply.recipient_id == "group42"

    @pytest.mark.asyncio
    async def test_reply_uses_sender_when_no_chat_id(self) -> None:
        from app.channels.routing.router_commands import RouterCommandsMixin

        handler = MagicMock()
        handler.list_background = AsyncMock(return_value=[])
        host = self._make_host(background_handler=handler)
        msg = _make_msg(channel="dm", sender_id="alice", chat_id=None)
        await RouterCommandsMixin._handle_background_command(host, msg, "list")

        reply: OutboundMessage = host._bus.publish_outbound.call_args[0][0]
        assert reply.recipient_id == "alice"


# ── Dispatch integration ───────────────────────────────────────────────


class TestDispatchBackgroundCommand:
    """Tests for BACKGROUND action in registry resolution."""

    def test_background_resolves(self) -> None:
        registry = CommandRegistry()
        result = registry.resolve("/background")
        assert result is not None
        assert result.command_def.action == CommandAction.BACKGROUND

    def test_btw_with_args(self) -> None:
        registry = CommandRegistry()
        result = registry.resolve("/btw research papers")
        assert result is not None
        assert result.raw_args == "research papers"

    def test_bg_with_list(self) -> None:
        registry = CommandRegistry()
        result = registry.resolve("/bg list")
        assert result is not None
        assert result.raw_args == "list"

    def test_btw_cancel_arg(self) -> None:
        registry = CommandRegistry()
        result = registry.resolve("/btw cancel bg_abc")
        assert result is not None
        assert result.raw_args == "cancel bg_abc"

    def test_btw_steer_arg(self) -> None:
        registry = CommandRegistry()
        result = registry.resolve("/btw steer bg_abc focus on security")
        assert result is not None
        assert result.raw_args == "steer bg_abc focus on security"
