"""Tests for /stop command — cancellation of active agent tasks.

Verifies that AgentRouter correctly detects /stop commands, cancels
active tasks via CancellationToken + asyncio.Task.cancel(), and
cleans up placeholder messages.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.channels.routing.command_defs import CommandAction
from app.channels.routing.command_registry import CommandRegistry


def _is_stop_command(content: str) -> bool:
    """Check via registry (replaces old is_stop_command pure function)."""
    registry = CommandRegistry()
    resolved = registry.resolve(content)
    return resolved is not None and resolved.command_def.action == CommandAction.STOP


from myrm_agent_harness.utils.runtime.cancellation import CancellationToken  # noqa: E402

from app.channels.routing.router import AgentRouter  # noqa: E402
from app.channels.routing.router_models import _ActiveTask  # noqa: E402
from app.channels.routing.session_gate import SessionGateConfig  # noqa: E402
from app.channels.types import InboundMessage, OutboundMessage  # noqa: E402

_NO_DEBOUNCE = SessionGateConfig(debounce_window_ms=0)


def _msg(
    channel: str = "telegram",
    sender_id: str = "user1",
    chat_id: str = "",
    content: str = "hello",
    message_id: str | None = "msg-001",
    user_id: str = "",
) -> InboundMessage:
    metadata: dict[str, object] = {}
    if message_id is not None:
        metadata["message_id"] = message_id
    return InboundMessage(
        channel=channel,
        sender_id=sender_id,
        chat_id=chat_id,
        content=content,
        metadata=metadata,
        user_id=user_id,
    )


@pytest.fixture()
def bus() -> MagicMock:
    from app.channels.core.bus import MessageBus

    real_bus = MessageBus()
    real_bus._ensure_queues()
    bus = MagicMock(wraps=real_bus)
    bus._inbound = real_bus._inbound
    bus.consume_inbound = real_bus.consume_inbound
    bus.publish_outbound = AsyncMock()
    bus.get_channel = MagicMock(return_value=None)
    return bus


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


class TestIsStopCommand:
    """Tests for _is_stop_command()."""

    def test_exact_stop(self) -> None:
        assert _is_stop_command("/stop") is True

    def test_stop_with_whitespace(self) -> None:
        assert _is_stop_command("  /stop  ") is True

    def test_stop_uppercase(self) -> None:
        assert _is_stop_command("/STOP") is True

    def test_stop_mixed_case(self) -> None:
        assert _is_stop_command("/Stop") is True

    def test_not_stop_with_args(self) -> None:
        assert _is_stop_command("/stop now") is False

    def test_not_stop_prefix(self) -> None:
        assert _is_stop_command("/stopping") is False

    def test_regular_message(self) -> None:
        assert _is_stop_command("hello world") is False

    def test_empty_string(self) -> None:
        assert _is_stop_command("") is False


class TestCancelActiveTask:
    """Tests for AgentRouter._cancel_active_task()."""

    @pytest.mark.asyncio
    async def test_no_active_task(self, router: AgentRouter, bus: MagicMock) -> None:
        """When no task is active, reply with informational message."""
        msg = _msg(content="/stop", sender_id="user1")
        await router._cancel_active_task(msg)

        bus.publish_outbound.assert_called_once()
        reply: OutboundMessage = bus.publish_outbound.call_args[0][0]
        assert "No active task" in reply.content

    @pytest.mark.asyncio
    async def test_cancels_active_task(self, router: AgentRouter, bus: MagicMock) -> None:
        """When a task is active, cancel it and reply with confirmation."""
        token = CancellationToken(request_id="test-req")
        mock_task = MagicMock(spec=asyncio.Task)
        mock_task.done.return_value = False

        router._active_tasks["telegram:user1"] = _ActiveTask(
            task=mock_task,
            cancel_token=token,
            channel="telegram",
            chat_id="user1",
            placeholder_id=None,
            started_at=0.0,
        )

        msg = _msg(content="/stop", sender_id="user1")
        await router._cancel_active_task(msg)

        assert token.is_cancelled
        assert token.cancel_reason == "User /stop command"
        mock_task.cancel.assert_called_once()

        assert "telegram:user1" not in router._active_tasks

        bus.publish_outbound.assert_called_once()
        reply: OutboundMessage = bus.publish_outbound.call_args[0][0]
        assert "stopped" in reply.content.lower()

    @pytest.mark.asyncio
    async def test_cancels_with_placeholder_cleanup(
        self,
        router: AgentRouter,
        bus: MagicMock,
    ) -> None:
        """Placeholder should be updated with stop message on cancellation."""
        token = CancellationToken(request_id="test-req")
        mock_task = MagicMock(spec=asyncio.Task)
        mock_task.done.return_value = False

        mock_channel = AsyncMock()
        bus.get_channel.return_value = mock_channel

        router._active_tasks["telegram:user1"] = _ActiveTask(
            task=mock_task,
            cancel_token=token,
            channel="telegram",
            chat_id="user1",
            placeholder_id="placeholder-123",
            started_at=0.0,
        )

        msg = _msg(content="/stop", sender_id="user1")
        await router._cancel_active_task(msg)

        mock_channel.edit_message.assert_called_once_with(
            "user1",
            "placeholder-123",
            "Execution stopped.",
        )

    @pytest.mark.asyncio
    async def test_already_done_task(self, router: AgentRouter, bus: MagicMock) -> None:
        """If the task is already done, cancel() should not be called."""
        token = CancellationToken(request_id="test-req")
        mock_task = MagicMock(spec=asyncio.Task)
        mock_task.done.return_value = True

        router._active_tasks["telegram:user1"] = _ActiveTask(
            task=mock_task,
            cancel_token=token,
            channel="telegram",
            chat_id="user1",
            placeholder_id=None,
            started_at=0.0,
        )

        msg = _msg(content="/stop", sender_id="user1")
        await router._cancel_active_task(msg)

        assert token.is_cancelled
        mock_task.cancel.assert_not_called()

    @pytest.mark.asyncio
    async def test_repeated_stop(self, router: AgentRouter, bus: MagicMock) -> None:
        """Second /stop should reply with 'no active task'."""
        token = CancellationToken(request_id="test-req")
        mock_task = MagicMock(spec=asyncio.Task)
        mock_task.done.return_value = False

        router._active_tasks["telegram:user1"] = _ActiveTask(
            task=mock_task,
            cancel_token=token,
            channel="telegram",
            chat_id="user1",
            placeholder_id=None,
            started_at=0.0,
        )

        msg = _msg(content="/stop", sender_id="user1")
        await router._cancel_active_task(msg)
        bus.publish_outbound.reset_mock()

        await router._cancel_active_task(msg)
        reply: OutboundMessage = bus.publish_outbound.call_args[0][0]
        assert "No active task" in reply.content


class TestHandleMessageStopIntegration:
    """Integration tests for /stop detection in _consume_loop via bus."""

    @pytest.mark.asyncio
    async def test_stop_command_dispatched(self, router: AgentRouter) -> None:
        """/stop messages sent via bus should dispatch to _cancel_active_task."""
        msg = _msg(content="/stop", message_id="stop-msg-1")

        with patch.object(router, "_cancel_active_task", new_callable=AsyncMock) as mock_cancel:
            await router.start()
            try:
                await router._bus._handle_inbound(msg)
                await asyncio.sleep(0.1)
                mock_cancel.assert_called_once()
            finally:
                await router.stop()

    @pytest.mark.asyncio
    async def test_stop_not_deduped_on_different_ids(self, router: AgentRouter) -> None:
        """Multiple /stop with different message_ids should all be processed."""
        with patch.object(router, "_cancel_active_task", new_callable=AsyncMock) as mock_cancel:
            await router.start()
            try:
                await router._bus._handle_inbound(_msg(content="/stop", message_id="stop-1"))
                await asyncio.sleep(0.05)
                await router._bus._handle_inbound(_msg(content="/stop", message_id="stop-2"))
                await asyncio.sleep(0.1)
                assert mock_cancel.call_count == 2
            finally:
                await router.stop()

    @pytest.mark.asyncio
    async def test_regular_message_not_stop(self, router: AgentRouter) -> None:
        """Regular messages should NOT trigger _cancel_active_task."""
        msg = _msg(content="hello", message_id="msg-regular")

        with patch.object(router, "_cancel_active_task", new_callable=AsyncMock) as mock_cancel:
            await router.start()
            try:
                await router._bus._handle_inbound(msg)
                await asyncio.sleep(0.5)
                mock_cancel.assert_not_called()
            finally:
                await router.stop()


class TestRouterStopCleansActiveTasks:
    """Tests for AgentRouter.stop() clearing active tasks."""

    @pytest.mark.asyncio
    async def test_stop_cancels_all_active_tasks(self, router: AgentRouter) -> None:
        token1 = CancellationToken(request_id="req-1")
        token2 = CancellationToken(request_id="req-2")
        task1 = MagicMock(spec=asyncio.Task)
        task1.done.return_value = False
        task2 = MagicMock(spec=asyncio.Task)
        task2.done.return_value = False

        router._active_tasks["telegram:chat1"] = _ActiveTask(
            task=task1,
            cancel_token=token1,
            channel="telegram",
            chat_id="chat1",
            placeholder_id=None,
            started_at=0.0,
        )
        router._active_tasks["whatsapp:chat2"] = _ActiveTask(
            task=task2,
            cancel_token=token2,
            channel="whatsapp",
            chat_id="chat2",
            placeholder_id=None,
            started_at=0.0,
        )

        await router.stop()

        assert token1.is_cancelled
        assert token2.is_cancelled
        task1.cancel.assert_called_once()
        task2.cancel.assert_called_once()
        assert len(router._active_tasks) == 0


class TestCancellationTokenIntegration:
    """Tests verifying CancellationToken behavior in stop flow."""

    def test_cancel_sets_reason(self) -> None:
        token = CancellationToken(request_id="test")
        token.cancel("User /stop command")
        assert token.is_cancelled
        assert token.cancel_reason == "User /stop command"

    def test_double_cancel_idempotent(self) -> None:
        token = CancellationToken(request_id="test")
        token.cancel("first")
        token.cancel("second")
        assert token.cancel_reason == "first"

    def test_check_cancelled_raises(self) -> None:
        token = CancellationToken(request_id="test")
        token.cancel("test")
        with pytest.raises(asyncio.CancelledError):
            token.check_cancelled("some_op")
