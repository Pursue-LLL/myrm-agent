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
