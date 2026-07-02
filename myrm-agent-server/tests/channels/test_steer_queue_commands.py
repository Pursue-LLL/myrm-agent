"""Tests for /steer and /queue slash commands — command_defs, dispatch, routing, integration."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from myrm_agent_harness.utils.runtime.cancellation import CancellationToken
from myrm_agent_harness.utils.runtime.steering import SteeringToken

from app.channels.routing.command_defs import (
    SYSTEM_COMMANDS,
    CommandAction,
)
from app.channels.routing.command_registry import (
    CommandRegistry,
)
from app.channels.routing.router import AgentRouter
from app.channels.routing.router_models import _ActiveTask
from app.channels.routing.session_gate import SessionGateConfig
from app.channels.types import InboundMessage, OutboundMessage


def _make_msg(content: str = "", channel: str = "test", sender: str = "user1") -> InboundMessage:
    return InboundMessage(channel=channel, sender_id=sender, content=content)


# ---- command_defs tests ----


class TestSteerCommandDef:
    """Tests for /steer CommandDef registration."""

    def test_steer_action_exists(self) -> None:
        assert hasattr(CommandAction, "STEER")
        assert CommandAction.STEER.value == "steer"

    def test_steer_in_system_commands(self) -> None:
        steer_cmds = [c for c in SYSTEM_COMMANDS if c.action == CommandAction.STEER]
        assert len(steer_cmds) == 1

    def test_steer_command_properties(self) -> None:
        steer_cmd = next(c for c in SYSTEM_COMMANDS if c.action == CommandAction.STEER)
        assert steer_cmd.name == "steer"
        assert steer_cmd.category == "Execution"
        assert steer_cmd.parse_args is True
        assert steer_cmd.args_pattern == "<new instruction>"

    def test_steer_registered_in_registry(self) -> None:
        registry = CommandRegistry()
        result = registry.resolve("/steer")
        assert result is not None
        assert result.command_def.action == CommandAction.STEER

    def test_steer_with_args(self) -> None:
        registry = CommandRegistry()
        result = registry.resolve("/steer use internal style")
        assert result is not None
        assert result.command_def.action == CommandAction.STEER
        assert result.raw_args == "use internal style"


class TestQueueCommandDef:
    """Tests for /queue CommandDef registration."""

    def test_queue_action_exists(self) -> None:
        assert hasattr(CommandAction, "QUEUE")
        assert CommandAction.QUEUE.value == "queue"

    def test_queue_in_system_commands(self) -> None:
        queue_cmds = [c for c in SYSTEM_COMMANDS if c.action == CommandAction.QUEUE]
        assert len(queue_cmds) == 1

    def test_queue_command_properties(self) -> None:
        queue_cmd = next(c for c in SYSTEM_COMMANDS if c.action == CommandAction.QUEUE)
        assert queue_cmd.name == "queue"
        assert queue_cmd.category == "Execution"
        assert queue_cmd.parse_args is True
        assert queue_cmd.args_pattern == "<task description>"

    def test_queue_registered_in_registry(self) -> None:
        registry = CommandRegistry()
        result = registry.resolve("/queue")
        assert result is not None
        assert result.command_def.action == CommandAction.QUEUE

    def test_queue_with_args(self) -> None:
        registry = CommandRegistry()
        result = registry.resolve("/queue organize my schedule")
        assert result is not None
        assert result.command_def.action == CommandAction.QUEUE
        assert result.raw_args == "organize my schedule"


# ---- _handle_steer_command tests ----


class TestHandleSteerCommand:
    """Tests for _handle_steer_command logic."""

    def _make_host(self, active_task: _ActiveTask | None = None) -> MagicMock:
        """Build a minimal RouterCommandsHost mock."""
        host = MagicMock()
        host._bus = MagicMock()
        host._bus.publish_outbound = AsyncMock()
        host._active_tasks = {}
        host._gate = MagicMock()
        host._gate.submit = MagicMock()
        if active_task:
            host._active_tasks["test:user1"] = active_task
        return host

    def _make_active_task(self) -> _ActiveTask:
        loop = asyncio.new_event_loop()
        task = loop.create_task(asyncio.sleep(100))
        active = _ActiveTask(
            task=task,
            cancel_token=CancellationToken(),
            channel="test",
            chat_id="user1",
            placeholder_id=None,
            started_at=0.0,
            steering_token=SteeringToken(),
        )
        loop.close()
        return active

    @pytest.mark.asyncio
    async def test_steer_no_args_shows_usage(self) -> None:
        from app.channels.routing.router_commands import (
            RouterCommandsMixin,
        )

        host = self._make_host()
        msg = _make_msg("/steer")

        await RouterCommandsMixin._handle_steer_command(host, msg, "")

        host._bus.publish_outbound.assert_called_once()
        reply: OutboundMessage = host._bus.publish_outbound.call_args[0][0]
        assert "Usage" in reply.content

    @pytest.mark.asyncio
    async def test_steer_with_active_task_injects_message(self) -> None:
        from app.channels.routing.router_commands import (
            RouterCommandsMixin,
        )

        steering_token = SteeringToken()
        task_mock = MagicMock()
        task_mock.done.return_value = False
        active = _ActiveTask(
            task=task_mock,
            cancel_token=CancellationToken(),
            channel="test",
            chat_id="user1",
            placeholder_id=None,
            started_at=0.0,
            steering_token=steering_token,
        )
        host = self._make_host(active)
        msg = _make_msg("/steer use internal format")

        await RouterCommandsMixin._handle_steer_command(host, msg, "use internal format")

        assert steering_token.has_pending
        host._bus.publish_outbound.assert_called_once()
        reply: OutboundMessage = host._bus.publish_outbound.call_args[0][0]
        assert "Steering applied" in reply.content
        assert "use internal format" in reply.content

    @pytest.mark.asyncio
    async def test_steer_no_active_task_submits_as_normal(self) -> None:
        from app.channels.routing.router_commands import (
            RouterCommandsMixin,
        )

        host = self._make_host()
        msg = _make_msg("/steer hello world")

        await RouterCommandsMixin._handle_steer_command(host, msg, "hello world")

        host._gate.submit.assert_called_once()
        submitted = host._gate.submit.call_args[0][0]
        assert submitted.content == "hello world"
        host._bus.publish_outbound.assert_not_called()


# ---- _handle_queue_command tests ----


class TestHandleQueueCommand:
    """Tests for _handle_queue_command logic."""

    def _make_host(self, active_task: _ActiveTask | None = None) -> MagicMock:
        host = MagicMock()
        host._bus = MagicMock()
        host._bus.publish_outbound = AsyncMock()
        host._active_tasks = {}
        host._gate = MagicMock()
        host._gate.submit = MagicMock()
        if active_task:
            host._active_tasks["test:user1"] = active_task
        return host

    @pytest.mark.asyncio
    async def test_queue_no_args_shows_usage(self) -> None:
        from app.channels.routing.router_commands import (
            RouterCommandsMixin,
        )

        host = self._make_host()
        msg = _make_msg("/queue")

        await RouterCommandsMixin._handle_queue_command(host, msg, "")

        host._bus.publish_outbound.assert_called_once()
        reply: OutboundMessage = host._bus.publish_outbound.call_args[0][0]
        assert "Usage" in reply.content

    @pytest.mark.asyncio
    async def test_queue_with_active_task_queues_and_confirms(self) -> None:
        from app.channels.routing.router_commands import (
            RouterCommandsMixin,
        )

        task_mock = MagicMock()
        task_mock.done.return_value = False
        active = _ActiveTask(
            task=task_mock,
            cancel_token=CancellationToken(),
            channel="test",
            chat_id="user1",
            placeholder_id=None,
            started_at=0.0,
            steering_token=SteeringToken(),
        )
        host = self._make_host(active)
        msg = _make_msg("/queue organize tomorrow")

        await RouterCommandsMixin._handle_queue_command(host, msg, "organize tomorrow")

        host._gate.submit.assert_called_once()
        submitted = host._gate.submit.call_args[0][0]
        assert submitted.content == "organize tomorrow"
        host._bus.publish_outbound.assert_called_once()
        reply: OutboundMessage = host._bus.publish_outbound.call_args[0][0]
        assert "Queued" in reply.content

    @pytest.mark.asyncio
    async def test_queue_no_active_task_executes_immediately(self) -> None:
        from app.channels.routing.router_commands import (
            RouterCommandsMixin,
        )

        host = self._make_host()
        msg = _make_msg("/queue do something")

        await RouterCommandsMixin._handle_queue_command(host, msg, "do something")

        host._gate.submit.assert_called_once()
        host._bus.publish_outbound.assert_called_once()
        reply: OutboundMessage = host._bus.publish_outbound.call_args[0][0]
        assert "immediately" in reply.content


# ---- SteeringToken integration ----


class TestSteeringTokenInActiveTask:
    """Test that _ActiveTask properly holds SteeringToken."""

    def test_active_task_has_steering_token_field(self) -> None:
        token = SteeringToken()
        task_mock = MagicMock()
        active = _ActiveTask(
            task=task_mock,
            cancel_token=CancellationToken(),
            channel="test",
            chat_id="user1",
            placeholder_id=None,
            started_at=0.0,
            steering_token=token,
        )
        assert active.steering_token is token

    def test_active_task_steering_token_defaults_none(self) -> None:
        task_mock = MagicMock()
        active = _ActiveTask(
            task=task_mock,
            cancel_token=CancellationToken(),
            channel="test",
            chat_id="user1",
            placeholder_id=None,
            started_at=0.0,
        )
        assert active.steering_token is None

    def test_steering_token_steer_makes_pending(self) -> None:
        token = SteeringToken()
        assert not token.has_pending
        token.steer("change direction")
        assert token.has_pending


# ---- Dispatch tests ----


class TestDispatchSystemCommand:
    """Verify that the AgentRouter._dispatch_system_command routes STEER/QUEUE."""

    def test_steer_resolve(self) -> None:
        registry = CommandRegistry()
        resolved = registry.resolve("/steer focus on section 2")
        assert resolved is not None
        assert resolved.command_def.action == CommandAction.STEER
        assert resolved.raw_args == "focus on section 2"

    def test_queue_resolve(self) -> None:
        registry = CommandRegistry()
        resolved = registry.resolve("/queue summarize the report")
        assert resolved is not None
        assert resolved.command_def.action == CommandAction.QUEUE
        assert resolved.raw_args == "summarize the report"

    def test_steer_case_insensitive(self) -> None:
        registry = CommandRegistry()
        resolved = registry.resolve("/STEER do something else")
        assert resolved is not None
        assert resolved.command_def.action == CommandAction.STEER

    def test_queue_case_insensitive(self) -> None:
        registry = CommandRegistry()
        resolved = registry.resolve("/QUEUE another task")
        assert resolved is not None
        assert resolved.command_def.action == CommandAction.QUEUE

    def test_steer_no_args_still_resolves(self) -> None:
        registry = CommandRegistry()
        resolved = registry.resolve("/steer")
        assert resolved is not None
        assert resolved.command_def.action == CommandAction.STEER
        assert resolved.raw_args == ""


class TestSteerCommandEdgeCases:
    """Edge case tests for /steer command."""

    def _make_host(self, active_task: _ActiveTask | None = None) -> MagicMock:
        host = MagicMock()
        host._bus = MagicMock()
        host._bus.publish_outbound = AsyncMock()
        host._active_tasks = {}
        host._gate = MagicMock()
        host._gate.submit = MagicMock()
        if active_task:
            host._active_tasks["test:user1"] = active_task
        return host

    @pytest.mark.asyncio
    async def test_steer_long_instruction_truncated_in_preview(self) -> None:
        from app.channels.routing.router_commands import (
            RouterCommandsMixin,
        )

        long_instruction = "x" * 200
        task_mock = MagicMock()
        task_mock.done.return_value = False
        steering_token = SteeringToken()
        active = _ActiveTask(
            task=task_mock,
            cancel_token=CancellationToken(),
            channel="test",
            chat_id="user1",
            placeholder_id=None,
            started_at=0.0,
            steering_token=steering_token,
        )
        host = self._make_host(active)
        msg = _make_msg(f"/steer {long_instruction}")

        await RouterCommandsMixin._handle_steer_command(host, msg, long_instruction)

        reply: OutboundMessage = host._bus.publish_outbound.call_args[0][0]
        assert "..." in reply.content
        assert len(reply.content) < 200

    @pytest.mark.asyncio
    async def test_steer_whitespace_only_shows_usage(self) -> None:
        from app.channels.routing.router_commands import (
            RouterCommandsMixin,
        )

        host = self._make_host()
        msg = _make_msg("/steer   ")

        await RouterCommandsMixin._handle_steer_command(host, msg, "   ")

        reply: OutboundMessage = host._bus.publish_outbound.call_args[0][0]
        assert "Usage" in reply.content

    @pytest.mark.asyncio
    async def test_steer_active_task_without_steering_token_fallback(self) -> None:
        """If _ActiveTask exists but steering_token is None, fall back to gate."""
        from app.channels.routing.router_commands import (
            RouterCommandsMixin,
        )

        task_mock = MagicMock()
        task_mock.done.return_value = False
        active = _ActiveTask(
            task=task_mock,
            cancel_token=CancellationToken(),
            channel="test",
            chat_id="user1",
            placeholder_id=None,
            started_at=0.0,
            steering_token=None,
        )
        host = self._make_host(active)
        msg = _make_msg("/steer new direction")

        await RouterCommandsMixin._handle_steer_command(host, msg, "new direction")

        host._gate.submit.assert_called_once()
        host._bus.publish_outbound.assert_not_called()


class TestQueueCommandEdgeCases:
    """Edge case tests for /queue command."""

    def _make_host(self, active_task: _ActiveTask | None = None) -> MagicMock:
        host = MagicMock()
        host._bus = MagicMock()
        host._bus.publish_outbound = AsyncMock()
        host._active_tasks = {}
        host._gate = MagicMock()
        host._gate.submit = MagicMock()
        if active_task:
            host._active_tasks["test:user1"] = active_task
        return host

    @pytest.mark.asyncio
    async def test_queue_whitespace_only_shows_usage(self) -> None:
        from app.channels.routing.router_commands import (
            RouterCommandsMixin,
        )

        host = self._make_host()
        msg = _make_msg("/queue   ")

        await RouterCommandsMixin._handle_queue_command(host, msg, "   ")

        reply: OutboundMessage = host._bus.publish_outbound.call_args[0][0]
        assert "Usage" in reply.content

    @pytest.mark.asyncio
    async def test_queue_preserves_message_channel_info(self) -> None:
        """Queued message should retain original channel/sender info."""
        from app.channels.routing.router_commands import (
            RouterCommandsMixin,
        )

        host = self._make_host()
        msg = InboundMessage(
            channel="telegram",
            sender_id="user123",
            content="/queue do the thing",
            chat_id="group456",
            is_group=True,
        )

        await RouterCommandsMixin._handle_queue_command(host, msg, "do the thing")

        submitted = host._gate.submit.call_args[0][0]
        assert submitted.channel == "telegram"
        assert submitted.sender_id == "user123"
        assert submitted.chat_id == "group456"
        assert submitted.content == "do the thing"


# ---- AgentRouter integration tests ----

_NO_DEBOUNCE = SessionGateConfig(debounce_window_ms=0)


@pytest.fixture()
def bus() -> MagicMock:
    from app.channels.core.bus import MessageBus

    real_bus = MessageBus()
    real_bus._ensure_queues()
    b = MagicMock(wraps=real_bus)
    b._inbound = real_bus._inbound
    b.consume_inbound = real_bus.consume_inbound
    b.publish_outbound = AsyncMock()
    b.get_channel = MagicMock(return_value=None)
    return b


@pytest.fixture()
def router(bus: MagicMock) -> AgentRouter:
    pairing = MagicMock()
    executor = AsyncMock()
    return AgentRouter(
        bus=bus,
        pairing_store=pairing,
        agent_executor=executor,
        session_gate_config=_NO_DEBOUNCE,
    )


class TestRouterSteerDispatch:
    """Integration tests: AgentRouter._dispatch_system_command with STEER/QUEUE."""

    @pytest.mark.asyncio
    async def test_dispatch_steer_with_active_task(self, router: AgentRouter, bus: MagicMock) -> None:
        """Full dispatch path: /steer -> _dispatch_system_command -> _handle_steer_command -> steer token."""
        steering_token = SteeringToken()
        mock_task = MagicMock(spec=asyncio.Task)
        mock_task.done.return_value = False

        router._active_tasks["telegram:user1"] = _ActiveTask(
            task=mock_task,
            cancel_token=CancellationToken(),
            channel="telegram",
            chat_id="user1",
            placeholder_id=None,
            started_at=0.0,
            steering_token=steering_token,
        )

        msg = InboundMessage(
            channel="telegram",
            sender_id="user1",
            content="/steer change to bullet points",
            metadata={"message_id": "msg-001"},
        )

        handled = await router._dispatch_system_command(msg, CommandAction.STEER, "change to bullet points")
        assert handled is True

        await asyncio.sleep(0.05)

        assert steering_token.has_pending

    @pytest.mark.asyncio
    async def test_dispatch_queue_returns_true(self, router: AgentRouter, bus: MagicMock) -> None:
        """Full dispatch path: /queue -> _dispatch_system_command returns True (consumed)."""
        msg = InboundMessage(
            channel="telegram",
            sender_id="user1",
            content="/queue do the next thing",
            metadata={"message_id": "msg-002"},
        )

        handled = await router._dispatch_system_command(msg, CommandAction.QUEUE, "do the next thing")
        assert handled is True

        await asyncio.sleep(0.05)

        calls = bus.publish_outbound.call_args_list
        assert len(calls) >= 1
        first_reply: OutboundMessage = calls[0][0][0]
        assert "immediately" in first_reply.content or "Queued" in first_reply.content
