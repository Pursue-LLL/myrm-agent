"""Tests for AgentRouter core logic: dedup, lifecycle, consume loop."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.channels.routing.router import AgentRouter
from app.channels.types import InboundMessage


def _make_bus() -> MagicMock:
    bus = MagicMock()
    bus.consume_inbound = AsyncMock(side_effect=TimeoutError)
    bus.publish_outbound = AsyncMock()
    bus.get_channel = MagicMock(return_value=None)
    return bus


def _make_router(**overrides: object) -> AgentRouter:
    bus = overrides.pop("bus", _make_bus())  # type: ignore[arg-type]
    pairing = overrides.pop("pairing", MagicMock())  # type: ignore[arg-type]
    executor = overrides.pop("executor", MagicMock())  # type: ignore[arg-type]
    return AgentRouter(
        bus=bus,
        pairing_store=pairing,
        agent_executor=executor,
        **overrides,  # type: ignore[arg-type]
    )


def _msg(
    content: str = "hello",
    channel: str = "test",
    sender_id: str = "user-1",
    message_id: str = "",
    chat_id: str = "chat-1",
) -> InboundMessage:
    return InboundMessage(
        channel=channel,
        sender_id=sender_id,
        content=content,
        chat_id=chat_id,
        message_id=message_id,
    )


# ── Dedup ─────────────────────────────────────────────────────────────


class TestRouterDedup:
    def test_no_message_id_not_duplicate(self) -> None:
        router = _make_router()
        msg = _msg(message_id="")
        assert router._is_duplicate(msg) is False
        assert router._is_duplicate(msg) is False

    def test_same_message_id_is_duplicate(self) -> None:
        router = _make_router()
        msg = _msg(message_id="m1")
        assert router._is_duplicate(msg) is False
        assert router._is_duplicate(msg) is True

    def test_different_channels_not_duplicate(self) -> None:
        router = _make_router()
        msg1 = _msg(message_id="m1", channel="telegram")
        msg2 = _msg(message_id="m1", channel="discord")
        assert router._is_duplicate(msg1) is False
        assert router._is_duplicate(msg2) is False

    def test_dedup_eviction_removes_expired(self) -> None:
        router = _make_router()
        router._seen_messages["test:old"] = time.monotonic() - 600
        from app.channels.routing.router_constants import _DEDUP_MAX_SIZE

        for i in range(_DEDUP_MAX_SIZE + 10):
            router._is_duplicate(_msg(message_id=f"m{i}"))
        assert "test:old" not in router._seen_messages


# ── Lifecycle ─────────────────────────────────────────────────────────


class TestRouterLifecycle:
    @pytest.mark.asyncio
    async def test_start_creates_task(self) -> None:
        router = _make_router()
        await router.start()
        assert router._running is True
        assert router._task is not None
        assert router._janitor_task is not None
        await router.stop()

    @pytest.mark.asyncio
    async def test_start_idempotent(self) -> None:
        router = _make_router()
        await router.start()
        task1 = router._task
        await router.start()
        assert router._task is task1
        await router.stop()

    @pytest.mark.asyncio
    async def test_stop_clears_state(self) -> None:
        router = _make_router()
        await router.start()
        router._seen_messages["test"] = time.monotonic()
        await router.stop()
        assert router._running is False
        assert router._task is None
        assert len(router._seen_messages) == 0
        assert len(router._active_tasks) == 0

    @pytest.mark.asyncio
    async def test_stop_cancels_active_tasks(self) -> None:
        router = _make_router()
        await router.start()

        mock_task = MagicMock()
        mock_task.done.return_value = False
        mock_task.cancel = MagicMock()
        mock_token = MagicMock()

        from app.channels.routing.router_models import _ActiveTask

        router._active_tasks["key1"] = _ActiveTask(
            task=mock_task,
            cancel_token=mock_token,
            channel="test",
            chat_id="chat-1",
            placeholder_id=None,
            started_at=0.0,
        )
        await router.stop()
        mock_token.cancel.assert_called_once()
        mock_task.cancel.assert_called_once()


# ── Consume loop ──────────────────────────────────────────────────────


class TestConsumeLoop:
    @pytest.mark.asyncio
    async def test_timeout_continues_loop(self) -> None:
        bus = _make_bus()
        call_count = 0

        async def side_effect() -> InboundMessage:
            nonlocal call_count
            call_count += 1
            if call_count >= 3:
                raise asyncio.CancelledError
            raise TimeoutError

        bus.consume_inbound = AsyncMock(side_effect=side_effect)
        router = _make_router(bus=bus)
        router._running = True
        await router._consume_loop()
        assert call_count >= 3

    @pytest.mark.asyncio
    async def test_stop_command_dispatched(self) -> None:
        bus = _make_bus()
        call_count = 0

        async def side_effect() -> InboundMessage:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _msg(content="/stop", message_id="s1")
            raise asyncio.CancelledError

        bus.consume_inbound = AsyncMock(side_effect=side_effect)
        router = _make_router(bus=bus)
        router._running = True
        router._cancel_active_task = AsyncMock()
        await router._consume_loop()
        await asyncio.sleep(0.05)

    @pytest.mark.asyncio
    async def test_duplicate_skipped(self) -> None:
        bus = _make_bus()
        call_count = 0

        async def side_effect() -> InboundMessage:
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                return _msg(content="hello", message_id="dup1")
            raise asyncio.CancelledError

        bus.consume_inbound = AsyncMock(side_effect=side_effect)
        router = _make_router(bus=bus)
        router._running = True
        router._gate = MagicMock()
        router._gate.submit = MagicMock()
        await router._consume_loop()
        assert router._gate.submit.call_count == 1

    @pytest.mark.asyncio
    async def test_normal_message_submitted_to_gate(self) -> None:
        bus = _make_bus()
        call_count = 0

        async def side_effect() -> InboundMessage:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _msg(content="hello", message_id="m1")
            raise asyncio.CancelledError

        bus.consume_inbound = AsyncMock(side_effect=side_effect)
        router = _make_router(bus=bus)
        router._running = True
        router._gate = MagicMock()
        router._gate.submit = MagicMock()
        await router._consume_loop()
        router._gate.submit.assert_called_once()

    @pytest.mark.asyncio
    async def test_new_session_command(self) -> None:
        bus = _make_bus()
        call_count = 0

        async def side_effect() -> InboundMessage:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _msg(content="/new", message_id="n1")
            raise asyncio.CancelledError

        bus.consume_inbound = AsyncMock(side_effect=side_effect)
        router = _make_router(bus=bus)
        router._running = True
        router._handle_new_session = AsyncMock()
        await router._consume_loop()
        await asyncio.sleep(0.05)


# ── Janitor ───────────────────────────────────────────────────────────


class TestJanitor:
    @pytest.mark.asyncio
    async def test_start_janitor_creates_task(self) -> None:
        router = _make_router()
        router._start_janitor()
        assert router._janitor_task is not None
        router._janitor_task.cancel()
        try:
            await router._janitor_task
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_stop_janitor(self) -> None:
        router = _make_router()
        router._start_janitor()
        await router._stop_janitor()


class TestReapStuckTasks:
    """Stuck task watchdog: detection, cancellation, resource cleanup, and SessionGate release."""

    @pytest.mark.asyncio
    async def test_stuck_task_cancelled_and_removed(self) -> None:
        """A task exceeding _STUCK_TASK_TIMEOUT is cancelled and removed from _active_tasks."""
        from app.channels.routing.router_constants import _STUCK_TASK_TIMEOUT
        from app.channels.routing.router_models import _ActiveTask

        router = _make_router()
        mock_task = MagicMock()
        mock_task.done.return_value = False
        mock_task.cancel = MagicMock()
        mock_token = MagicMock()

        state_key = "test:chat-1"
        router._active_tasks[state_key] = _ActiveTask(
            task=mock_task,
            cancel_token=mock_token,
            channel="test",
            chat_id="chat-1",
            placeholder_id=None,
            started_at=time.monotonic() - _STUCK_TASK_TIMEOUT - 10,
        )

        router._fx = MagicMock()
        router._fx.stop_typing_keepalive = AsyncMock()
        router._fx.set_typing = AsyncMock()
        router._gate = MagicMock()
        router._gate.on_task_complete = MagicMock()

        await router._reap_stuck_tasks(time.monotonic())

        mock_token.cancel.assert_called_once()
        mock_task.cancel.assert_called_once()
        assert state_key not in router._active_tasks

    @pytest.mark.asyncio
    async def test_non_stuck_task_untouched(self) -> None:
        """A task within timeout is not cancelled."""
        from app.channels.routing.router_models import _ActiveTask

        router = _make_router()
        mock_task = MagicMock()
        mock_task.done.return_value = False
        mock_token = MagicMock()

        state_key = "test:chat-1"
        router._active_tasks[state_key] = _ActiveTask(
            task=mock_task,
            cancel_token=mock_token,
            channel="test",
            chat_id="chat-1",
            placeholder_id=None,
            started_at=time.monotonic() - 10,
        )

        router._fx = MagicMock()
        router._gate = MagicMock()

        await router._reap_stuck_tasks(time.monotonic())

        mock_token.cancel.assert_not_called()
        mock_task.cancel.assert_not_called()
        assert state_key in router._active_tasks

    @pytest.mark.asyncio
    async def test_already_done_task_skipped(self) -> None:
        """A task that has already completed (done=True) is not reaped even if old."""
        from app.channels.routing.router_constants import _STUCK_TASK_TIMEOUT
        from app.channels.routing.router_models import _ActiveTask

        router = _make_router()
        mock_task = MagicMock()
        mock_task.done.return_value = True
        mock_token = MagicMock()

        state_key = "test:chat-1"
        router._active_tasks[state_key] = _ActiveTask(
            task=mock_task,
            cancel_token=mock_token,
            channel="test",
            chat_id="chat-1",
            placeholder_id=None,
            started_at=time.monotonic() - _STUCK_TASK_TIMEOUT - 100,
        )

        router._fx = MagicMock()
        router._gate = MagicMock()

        await router._reap_stuck_tasks(time.monotonic())

        mock_token.cancel.assert_not_called()
        assert state_key in router._active_tasks

    @pytest.mark.asyncio
    async def test_session_gate_released(self) -> None:
        """SessionGate.on_task_complete is called to unblock the session."""
        from app.channels.routing.router_constants import _STUCK_TASK_TIMEOUT
        from app.channels.routing.router_models import _ActiveTask

        router = _make_router()
        mock_task = MagicMock()
        mock_task.done.return_value = False
        mock_token = MagicMock()

        router._active_tasks["test:chat-1"] = _ActiveTask(
            task=mock_task,
            cancel_token=mock_token,
            channel="test",
            chat_id="chat-1",
            placeholder_id=None,
            started_at=time.monotonic() - _STUCK_TASK_TIMEOUT - 10,
        )

        router._fx = MagicMock()
        router._fx.stop_typing_keepalive = AsyncMock()
        router._fx.set_typing = AsyncMock()
        router._gate = MagicMock()
        router._gate.on_task_complete = MagicMock()

        await router._reap_stuck_tasks(time.monotonic())

        router._gate.on_task_complete.assert_called_once()
        call_msg = router._gate.on_task_complete.call_args[0][0]
        assert call_msg.channel == "test"
        assert call_msg.chat_id == "chat-1"

    @pytest.mark.asyncio
    async def test_locale_preserved_in_synthetic_msg(self) -> None:
        """Synthetic msg carries the original locale so i18n resolves correctly."""
        from app.channels.routing.router_constants import _STUCK_TASK_TIMEOUT
        from app.channels.routing.router_models import _ActiveTask

        router = _make_router()
        mock_task = MagicMock()
        mock_task.done.return_value = False
        mock_token = MagicMock()

        router._active_tasks["test:chat-1"] = _ActiveTask(
            task=mock_task,
            cancel_token=mock_token,
            channel="test",
            chat_id="chat-1",
            placeholder_id=None,
            started_at=time.monotonic() - _STUCK_TASK_TIMEOUT - 10,
            locale="ja",
        )

        router._fx = MagicMock()
        router._fx.stop_typing_keepalive = AsyncMock()
        router._fx.set_typing = AsyncMock()
        router._gate = MagicMock()
        router._gate.on_task_complete = MagicMock()

        await router._reap_stuck_tasks(time.monotonic())

        call_msg = router._gate.on_task_complete.call_args[0][0]
        assert call_msg.metadata is not None
        assert call_msg.metadata["locale"] == "ja"

    @pytest.mark.asyncio
    async def test_typing_and_placeholder_cleaned(self) -> None:
        """Typing indicators are stopped and placeholder is cleaned up for stuck tasks."""
        from app.channels.routing.router_constants import _STUCK_TASK_TIMEOUT
        from app.channels.routing.router_models import _ActiveTask

        router = _make_router()
        mock_task = MagicMock()
        mock_task.done.return_value = False
        mock_token = MagicMock()

        router._active_tasks["test:chat-1"] = _ActiveTask(
            task=mock_task,
            cancel_token=mock_token,
            channel="test",
            chat_id="chat-1",
            placeholder_id="ph-123",
            started_at=time.monotonic() - _STUCK_TASK_TIMEOUT - 10,
        )

        router._fx = MagicMock()
        router._fx.stop_typing_keepalive = AsyncMock()
        router._fx.set_typing = AsyncMock()
        router._fx.cleanup_placeholder = AsyncMock()
        router._gate = MagicMock()
        router._gate.on_task_complete = MagicMock()

        await router._reap_stuck_tasks(time.monotonic())

        router._fx.stop_typing_keepalive.assert_called_once_with("test", "chat-1")
        router._fx.set_typing.assert_called_once_with("test", "chat-1", composing=False)
        router._fx.cleanup_placeholder.assert_called_once()
        ph_args = router._fx.cleanup_placeholder.call_args
        assert ph_args[0][0] == "test"
        assert ph_args[0][1] == "chat-1"
        assert ph_args[0][2] == "ph-123"

    @pytest.mark.asyncio
    async def test_multiple_stuck_tasks_all_reaped(self) -> None:
        """Multiple stuck tasks are all reaped in a single pass."""
        from app.channels.routing.router_constants import _STUCK_TASK_TIMEOUT
        from app.channels.routing.router_models import _ActiveTask

        router = _make_router()
        for i in range(3):
            mock_task = MagicMock()
            mock_task.done.return_value = False
            mock_token = MagicMock()
            router._active_tasks[f"test:chat-{i}"] = _ActiveTask(
                task=mock_task,
                cancel_token=mock_token,
                channel="test",
                chat_id=f"chat-{i}",
                placeholder_id=None,
                started_at=time.monotonic() - _STUCK_TASK_TIMEOUT - 10,
            )

        router._fx = MagicMock()
        router._fx.stop_typing_keepalive = AsyncMock()
        router._fx.set_typing = AsyncMock()
        router._gate = MagicMock()
        router._gate.on_task_complete = MagicMock()

        await router._reap_stuck_tasks(time.monotonic())

        assert len(router._active_tasks) == 0
        assert router._gate.on_task_complete.call_count == 3

    @pytest.mark.asyncio
    async def test_approval_state_cleaned_on_stuck(self) -> None:
        """Pending approval state for a stuck task is cleaned up."""
        from app.channels.routing.router_constants import _STUCK_TASK_TIMEOUT
        from app.channels.routing.router_models import _ActiveTask

        router = _make_router()
        mock_task = MagicMock()
        mock_task.done.return_value = False
        mock_token = MagicMock()

        state_key = "test:chat-1"
        router._active_tasks[state_key] = _ActiveTask(
            task=mock_task,
            cancel_token=mock_token,
            channel="test",
            chat_id="chat-1",
            placeholder_id=None,
            started_at=time.monotonic() - _STUCK_TASK_TIMEOUT - 10,
        )
        router._approval_msg_ids[state_key] = "approval-msg-1"

        router._fx = MagicMock()
        router._fx.stop_typing_keepalive = AsyncMock()
        router._fx.set_typing = AsyncMock()
        router._gate = MagicMock()
        router._gate.on_task_complete = MagicMock()

        await router._reap_stuck_tasks(time.monotonic())

        assert state_key not in router._active_tasks
        assert state_key not in router._approval_msg_ids

    @pytest.mark.asyncio
    async def test_empty_locale_fallback_no_metadata(self) -> None:
        """Empty locale produces synthetic msg with metadata=None (i18n falls back to English)."""
        from app.channels.routing.router_constants import _STUCK_TASK_TIMEOUT
        from app.channels.routing.router_models import _ActiveTask

        router = _make_router()
        mock_task = MagicMock()
        mock_task.done.return_value = False
        mock_token = MagicMock()

        router._active_tasks["test:chat-1"] = _ActiveTask(
            task=mock_task,
            cancel_token=mock_token,
            channel="test",
            chat_id="chat-1",
            placeholder_id=None,
            started_at=time.monotonic() - _STUCK_TASK_TIMEOUT - 10,
            locale="",
        )

        router._fx = MagicMock()
        router._fx.stop_typing_keepalive = AsyncMock()
        router._fx.set_typing = AsyncMock()
        router._gate = MagicMock()
        router._gate.on_task_complete = MagicMock()

        await router._reap_stuck_tasks(time.monotonic())

        call_msg = router._gate.on_task_complete.call_args[0][0]
        assert call_msg.metadata is None

    @pytest.mark.asyncio
    async def test_typing_error_does_not_block_gate_release(self) -> None:
        """Typing cleanup failure does not prevent SessionGate release."""
        from app.channels.routing.router_constants import _STUCK_TASK_TIMEOUT
        from app.channels.routing.router_models import _ActiveTask

        router = _make_router()
        mock_task = MagicMock()
        mock_task.done.return_value = False
        mock_token = MagicMock()

        router._active_tasks["test:chat-1"] = _ActiveTask(
            task=mock_task,
            cancel_token=mock_token,
            channel="test",
            chat_id="chat-1",
            placeholder_id=None,
            started_at=time.monotonic() - _STUCK_TASK_TIMEOUT - 10,
        )

        router._fx = MagicMock()
        router._fx.stop_typing_keepalive = AsyncMock(side_effect=RuntimeError("network down"))
        router._fx.set_typing = AsyncMock()
        router._gate = MagicMock()
        router._gate.on_task_complete = MagicMock()

        await router._reap_stuck_tasks(time.monotonic())

        router._gate.on_task_complete.assert_called_once()
        assert "test:chat-1" not in router._active_tasks

    @pytest.mark.asyncio
    async def test_no_placeholder_skips_placeholder_cleanup(self) -> None:
        """When placeholder_id is None, cleanup_placeholder is not called."""
        from app.channels.routing.router_constants import _STUCK_TASK_TIMEOUT
        from app.channels.routing.router_models import _ActiveTask

        router = _make_router()
        mock_task = MagicMock()
        mock_task.done.return_value = False
        mock_token = MagicMock()

        router._active_tasks["test:chat-1"] = _ActiveTask(
            task=mock_task,
            cancel_token=mock_token,
            channel="test",
            chat_id="chat-1",
            placeholder_id=None,
            started_at=time.monotonic() - _STUCK_TASK_TIMEOUT - 10,
        )

        router._fx = MagicMock()
        router._fx.stop_typing_keepalive = AsyncMock()
        router._fx.set_typing = AsyncMock()
        router._fx.cleanup_placeholder = AsyncMock()
        router._gate = MagicMock()
        router._gate.on_task_complete = MagicMock()

        await router._reap_stuck_tasks(time.monotonic())

        router._fx.cleanup_placeholder.assert_not_called()


class TestHandleMerged:
    @pytest.mark.asyncio
    async def test_channel_capabilities_populated(self) -> None:
        from app.channels.types import ChannelCapabilities

        bus = _make_bus()
        mock_channel = MagicMock()
        mock_channel.capabilities = ChannelCapabilities(media=False, buttons=True)
        bus.get_channel.return_value = mock_channel

        router = _make_router(bus=bus)
        # Mock _prepare_execution_context to stop execution early
        router._prepare_execution_context = AsyncMock(return_value=None)

        msg = _msg(channel="test_channel")
        assert msg.channel_capabilities is None

        await router._handle_merged(msg)

        # Verify get_channel was called
        bus.get_channel.assert_called_once_with("test_channel")
        # Verify the message passed to _prepare_execution_context has capabilities
        router._prepare_execution_context.assert_called_once()
        called_msg = router._prepare_execution_context.call_args[0][0]
        assert called_msg.channel_capabilities is not None
        assert called_msg.channel_capabilities.media is False
        assert called_msg.channel_capabilities.buttons is True

    @pytest.mark.asyncio
    async def test_channel_capabilities_not_overwritten(self) -> None:
        from app.channels.types import ChannelCapabilities

        bus = _make_bus()
        mock_channel = MagicMock()
        mock_channel.capabilities = ChannelCapabilities(media=False)
        bus.get_channel.return_value = mock_channel

        router = _make_router(bus=bus)
        router._prepare_execution_context = AsyncMock(return_value=None)

        import dataclasses

        msg = _msg(channel="test_channel")
        msg = dataclasses.replace(msg, channel_capabilities=ChannelCapabilities(media=True))

        await router._handle_merged(msg)

        called_msg = router._prepare_execution_context.call_args[0][0]
        # Should retain the original capabilities
        assert called_msg.channel_capabilities.media is True


# ── Admin permission ──────────────────────────────────────────────────


class TestAdminPermission:
    def test_no_checker_allows_all(self) -> None:
        router = _make_router()
        msg = _msg()
        assert router._check_admin_permission(msg) is True

    def test_checker_returns_true(self) -> None:
        checker = MagicMock(return_value=True)
        router = _make_router(admin_checker=checker)
        msg = _msg()
        assert router._check_admin_permission(msg) is True
        checker.assert_called_once_with(msg)

    def test_checker_returns_false(self) -> None:
        checker = MagicMock(return_value=False)
        router = _make_router(admin_checker=checker)
        msg = _msg()
        assert router._check_admin_permission(msg) is False

    @pytest.mark.asyncio
    async def test_admin_denied_sends_permission_message(self) -> None:
        from app.channels.routing.command_defs import CommandDef, CommandKind
        from app.channels.routing.command_registry import ResolvedCommand

        bus = _make_bus()
        checker = MagicMock(return_value=False)
        router = _make_router(bus=bus, admin_checker=checker)

        cmd = CommandDef(
            name="yolo",
            kind=CommandKind.SYSTEM,
            description="Toggle YOLO mode",
            requires_admin=True,
        )
        resolved = ResolvedCommand(command_def=cmd, raw_args="on")
        msg = _msg(content="/yolo on")

        result = await router._dispatch_resolved(msg, resolved)

        assert result is True
        bus.publish_outbound.assert_called_once()
        reply = bus.publish_outbound.call_args[0][0]
        assert "Permission denied" in reply.content
        assert "/yolo" in reply.content

    @pytest.mark.asyncio
    async def test_admin_allowed_proceeds(self) -> None:
        from app.channels.routing.command_defs import CommandAction, CommandDef, CommandKind
        from app.channels.routing.command_registry import ResolvedCommand

        bus = _make_bus()
        checker = MagicMock(return_value=True)
        router = _make_router(bus=bus, admin_checker=checker)

        cmd = CommandDef(
            name="yolo",
            kind=CommandKind.SYSTEM,
            action=CommandAction.YOLO,
            description="Toggle YOLO mode",
            requires_admin=True,
        )
        resolved = ResolvedCommand(command_def=cmd, raw_args="on")
        msg = _msg(content="/yolo on")
        router._dispatch_system_command = AsyncMock(return_value=True)

        result = await router._dispatch_resolved(msg, resolved)

        assert result is True
        router._dispatch_system_command.assert_called_once()
        bus.publish_outbound.assert_not_called()
