"""Tests for GoalTerminalNotifier."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.event.app_event_bus import AppEventType, ServerEventBus


def _make_event_bus() -> ServerEventBus:
    return ServerEventBus()


def _goal_event_data(
    *,
    channel: str = "feishu",
    chat_id: str = "g123",
    thread_id: str = "th456",
    status: str = "complete",
    objective: str = "deploy my app",
    session_id: str = "sess-1",
    files_modified: int = 5,
    turns_used: int = 12,
    execution_duration_s: float = 360.0,
    total_tokens: int = 50000,
    total_cost_usd: float = 0.42,
) -> dict[str, object]:
    return {
        "goal_id": "g-001",
        "session_id": session_id,
        "status": status,
        "objective": objective,
        "files_modified": files_modified,
        "total_tokens": total_tokens,
        "total_cost_usd": total_cost_usd,
        "execution_duration_s": execution_duration_s,
        "turns_used": turns_used,
        "verifications": (),
        "channel": channel,
        "chat_id": chat_id,
        "thread_id": thread_id,
    }


class TestGoalTerminalNotifier:
    """Unit tests for GoalTerminalNotifier lifecycle and delivery."""

    @pytest.mark.asyncio
    async def test_start_stop_lifecycle(self) -> None:
        from app.core.channel_bridge.goal_terminal_notifier import GoalTerminalNotifier

        bus = _make_event_bus()
        notifier = GoalTerminalNotifier(bus)

        await notifier.start()
        assert notifier._task is not None
        assert notifier._queue is not None

        await notifier.stop()
        assert notifier._task is None
        assert notifier._queue is None

    @pytest.mark.asyncio
    async def test_stop_when_not_started(self) -> None:
        from app.core.channel_bridge.goal_terminal_notifier import GoalTerminalNotifier

        bus = _make_event_bus()
        notifier = GoalTerminalNotifier(bus)
        await notifier.stop()
        assert notifier._task is None

    @pytest.mark.asyncio
    async def test_deliver_sends_to_channel(self) -> None:
        from app.core.channel_bridge.goal_terminal_notifier import GoalTerminalNotifier

        bus = _make_event_bus()
        notifier = GoalTerminalNotifier(bus)

        from app.channels.types.status import ChannelStatus

        mock_channel = MagicMock()
        mock_channel.status = ChannelStatus.RUNNING
        mock_channel.send = AsyncMock()
        mock_channel.retry_config = MagicMock()
        mock_channel.should_retry = MagicMock(return_value=False)
        mock_channel.extract_retry_after = MagicMock(return_value=None)
        mock_channel.activity = MagicMock()

        mock_gateway = MagicMock()
        mock_gateway.bus.channels.get.return_value = mock_channel
        mock_send_with_retry = AsyncMock()

        with (
            patch(
                "app.core.channel_bridge.goal_terminal_notifier.channel_t",
                return_value="Goal completed notification",
            ),
            patch("app.channels.reliability.retry.send_with_retry", mock_send_with_retry),
            patch("app.channels.core.bus.downgrade_components", side_effect=lambda m, c: m),
            patch("app.core.channel_bridge.channel_gateway", mock_gateway),
        ):
            await notifier._deliver(_goal_event_data())

            mock_send_with_retry.assert_called_once()
            sent_msg = mock_send_with_retry.call_args[0][1]
            assert sent_msg.channel == "feishu"
            assert sent_msg.recipient_id == "g123"
            assert sent_msg.content == "Goal completed notification"

    @pytest.mark.asyncio
    async def test_deliver_skips_missing_channel(self) -> None:
        from app.core.channel_bridge.goal_terminal_notifier import GoalTerminalNotifier

        bus = _make_event_bus()
        notifier = GoalTerminalNotifier(bus)

        mock_gateway = MagicMock()
        mock_gateway.bus.channels.get.return_value = None

        with (
            patch(
                "app.core.channel_bridge.goal_terminal_notifier.channel_t",
                return_value="msg",
            ),
            patch("app.core.channel_bridge.channel_gateway", mock_gateway),
        ):
            await notifier._deliver(_goal_event_data(channel="nonexistent"))

    @pytest.mark.asyncio
    async def test_deliver_skips_empty_channel(self) -> None:
        from app.core.channel_bridge.goal_terminal_notifier import GoalTerminalNotifier

        bus = _make_event_bus()
        notifier = GoalTerminalNotifier(bus)
        await notifier._deliver(_goal_event_data(channel="", chat_id="c1"))

    @pytest.mark.asyncio
    async def test_deliver_skips_empty_chat_id(self) -> None:
        from app.core.channel_bridge.goal_terminal_notifier import GoalTerminalNotifier

        bus = _make_event_bus()
        notifier = GoalTerminalNotifier(bus)
        await notifier._deliver(_goal_event_data(channel="feishu", chat_id=""))

    @pytest.mark.asyncio
    async def test_deliver_skips_stopped_channel(self) -> None:
        from app.core.channel_bridge.goal_terminal_notifier import GoalTerminalNotifier

        bus = _make_event_bus()
        notifier = GoalTerminalNotifier(bus)

        from app.channels.types.status import ChannelStatus

        mock_channel = MagicMock()
        mock_channel.status = ChannelStatus.STOPPED
        mock_channel.send = AsyncMock()

        mock_gateway = MagicMock()
        mock_gateway.bus.channels.get.return_value = mock_channel

        with (
            patch(
                "app.core.channel_bridge.goal_terminal_notifier.channel_t",
                return_value="msg",
            ),
            patch("app.core.channel_bridge.channel_gateway", mock_gateway),
        ):
            await notifier._deliver(_goal_event_data())

        mock_channel.send.assert_not_called()

    @pytest.mark.asyncio
    async def test_deliver_includes_thread_id_metadata(self) -> None:
        from app.core.channel_bridge.goal_terminal_notifier import GoalTerminalNotifier

        bus = _make_event_bus()
        notifier = GoalTerminalNotifier(bus)

        from app.channels.types.status import ChannelStatus

        mock_channel = MagicMock()
        mock_channel.status = ChannelStatus.RUNNING
        mock_channel.activity = MagicMock()
        mock_send_with_retry = AsyncMock()

        mock_gateway = MagicMock()
        mock_gateway.bus.channels.get.return_value = mock_channel

        with (
            patch(
                "app.core.channel_bridge.goal_terminal_notifier.channel_t",
                return_value="msg",
            ),
            patch("app.channels.reliability.retry.send_with_retry", mock_send_with_retry),
            patch("app.channels.core.bus.downgrade_components", side_effect=lambda m, c: m),
            patch("app.core.channel_bridge.channel_gateway", mock_gateway),
        ):
            await notifier._deliver(_goal_event_data(thread_id="t789"))

            sent_msg = mock_send_with_retry.call_args[0][1]
            assert sent_msg.metadata == {"thread_id": "t789"}

    @pytest.mark.asyncio
    async def test_deliver_no_thread_id_metadata_is_none(self) -> None:
        from app.core.channel_bridge.goal_terminal_notifier import GoalTerminalNotifier

        bus = _make_event_bus()
        notifier = GoalTerminalNotifier(bus)

        from app.channels.types.status import ChannelStatus

        mock_channel = MagicMock()
        mock_channel.status = ChannelStatus.RUNNING
        mock_channel.activity = MagicMock()
        mock_send_with_retry = AsyncMock()

        mock_gateway = MagicMock()
        mock_gateway.bus.channels.get.return_value = mock_channel

        with (
            patch(
                "app.core.channel_bridge.goal_terminal_notifier.channel_t",
                return_value="msg",
            ),
            patch("app.channels.reliability.retry.send_with_retry", mock_send_with_retry),
            patch("app.channels.core.bus.downgrade_components", side_effect=lambda m, c: m),
            patch("app.core.channel_bridge.channel_gateway", mock_gateway),
        ):
            await notifier._deliver(_goal_event_data(thread_id=""))

            sent_msg = mock_send_with_retry.call_args[0][1]
            assert sent_msg.metadata is None

    @pytest.mark.asyncio
    async def test_deliver_handles_send_failure(self) -> None:
        from app.core.channel_bridge.goal_terminal_notifier import GoalTerminalNotifier

        bus = _make_event_bus()
        notifier = GoalTerminalNotifier(bus)

        from app.channels.types.status import ChannelStatus

        mock_channel = MagicMock()
        mock_channel.status = ChannelStatus.RUNNING
        mock_channel.activity = MagicMock()
        mock_send_with_retry = AsyncMock(side_effect=ConnectionError("network down"))

        mock_gateway = MagicMock()
        mock_gateway.bus.channels.get.return_value = mock_channel

        with (
            patch(
                "app.core.channel_bridge.goal_terminal_notifier.channel_t",
                return_value="msg",
            ),
            patch("app.channels.reliability.retry.send_with_retry", mock_send_with_retry),
            patch("app.channels.core.bus.downgrade_components", side_effect=lambda m, c: m),
            patch("app.core.channel_bridge.channel_gateway", mock_gateway),
        ):
            await notifier._deliver(_goal_event_data())

        mock_channel.activity.record_error.assert_called_once()

    @pytest.mark.asyncio
    async def test_deliver_adds_deeplink_components(self) -> None:
        from app.channels.types.components import ActionButton, ButtonStyle
        from app.core.channel_bridge.goal_terminal_notifier import GoalTerminalNotifier

        bus = _make_event_bus()
        notifier = GoalTerminalNotifier(bus)

        from app.channels.types.status import ChannelStatus

        mock_channel = MagicMock()
        mock_channel.status = ChannelStatus.RUNNING
        mock_channel.activity = MagicMock()
        mock_send_with_retry = AsyncMock()

        mock_gateway = MagicMock()
        mock_gateway.bus.channels.get.return_value = mock_channel

        deep_link_components = (
            (
                ActionButton(
                    label="View details",
                    action_id="web:open_chat",
                    style=ButtonStyle.PRIMARY,
                    url="https://example.com/chat/sess-1",
                ),
            ),
        )

        with (
            patch(
                "app.core.channel_bridge.goal_terminal_notifier.channel_t",
                return_value="msg",
            ),
            patch("app.channels.reliability.retry.send_with_retry", mock_send_with_retry),
            patch("app.channels.core.bus.downgrade_components", side_effect=lambda m, c: m),
            patch("app.core.channel_bridge.channel_gateway", mock_gateway),
            patch(
                "app.remote_access.mobile_deep_link.resolve_web_handoff_components",
                AsyncMock(return_value=deep_link_components),
            ),
        ):
            await notifier._deliver(_goal_event_data(session_id="sess-1"))

            sent_msg = mock_send_with_retry.call_args[0][1]
            assert sent_msg.components == deep_link_components


    @pytest.mark.asyncio
    async def test_deliver_uses_locale_from_event_data(self) -> None:
        from app.core.channel_bridge.goal_terminal_notifier import GoalTerminalNotifier

        bus = _make_event_bus()
        notifier = GoalTerminalNotifier(bus)

        from app.channels.types.status import ChannelStatus

        mock_channel = MagicMock()
        mock_channel.status = ChannelStatus.RUNNING
        mock_channel.activity = MagicMock()
        mock_send_with_retry = AsyncMock()

        mock_gateway = MagicMock()
        mock_gateway.bus.channels.get.return_value = mock_channel

        data = _goal_event_data()
        data["locale"] = "ja"

        with (
            patch(
                "app.core.channel_bridge.goal_terminal_notifier.channel_t",
                return_value="ja notification",
            ) as mock_t,
            patch("app.channels.reliability.retry.send_with_retry", mock_send_with_retry),
            patch("app.channels.core.bus.downgrade_components", side_effect=lambda m, c: m),
            patch("app.core.channel_bridge.channel_gateway", mock_gateway),
        ):
            await notifier._deliver(data)

            assert mock_t.call_args[0][0] == "ja"

    @pytest.mark.asyncio
    async def test_deliver_defaults_locale_to_en(self) -> None:
        from app.core.channel_bridge.goal_terminal_notifier import GoalTerminalNotifier

        bus = _make_event_bus()
        notifier = GoalTerminalNotifier(bus)

        from app.channels.types.status import ChannelStatus

        mock_channel = MagicMock()
        mock_channel.status = ChannelStatus.RUNNING
        mock_channel.activity = MagicMock()
        mock_send_with_retry = AsyncMock()

        mock_gateway = MagicMock()
        mock_gateway.bus.channels.get.return_value = mock_channel

        data = _goal_event_data()
        assert "locale" not in data

        with (
            patch(
                "app.core.channel_bridge.goal_terminal_notifier.channel_t",
                return_value="en notification",
            ) as mock_t,
            patch("app.channels.reliability.retry.send_with_retry", mock_send_with_retry),
            patch("app.channels.core.bus.downgrade_components", side_effect=lambda m, c: m),
            patch("app.core.channel_bridge.channel_gateway", mock_gateway),
        ):
            await notifier._deliver(data)

            assert mock_t.call_args[0][0] == "en"


class TestFormatGoalNotification:
    """Unit tests for _format_goal_notification."""

    def test_completed_status(self) -> None:
        with patch(
            "app.core.channel_bridge.goal_terminal_notifier.channel_t",
            return_value="  ok  ",
        ) as mock_t:
            from app.core.channel_bridge.goal_terminal_notifier import _format_goal_notification

            result = _format_goal_notification(
                _goal_event_data(status="complete"),
                "complete",
                "deploy my app",
                "en",
            )
            assert result == "ok"
            mock_t.assert_called_once_with(
                "en",
                "goal_completed",
                objective="deploy my app",
                turns=12,
                duration=6.0,
                files=5,
            )

    def test_failed_status(self) -> None:
        with patch(
            "app.core.channel_bridge.goal_terminal_notifier.channel_t",
        ) as mock_t:
            mock_t.return_value = "failed msg"
            from app.core.channel_bridge.goal_terminal_notifier import _format_goal_notification

            _format_goal_notification(
                _goal_event_data(status="cancelled"),
                "cancelled",
                "build feature",
                "zh-CN",
            )
            mock_t.assert_called_once_with(
                "zh-CN",
                "goal_failed",
                objective="build feature",
                turns=12,
                duration=6.0,
                files=5,
            )

    def test_objective_truncation(self) -> None:
        with patch(
            "app.core.channel_bridge.goal_terminal_notifier.channel_t",
        ) as mock_t:
            mock_t.return_value = "msg"
            from app.core.channel_bridge.goal_terminal_notifier import _format_goal_notification

            long_objective = "x" * 200
            _format_goal_notification(
                _goal_event_data(objective=long_objective),
                "complete",
                long_objective,
                "en",
            )
            call_kwargs = mock_t.call_args[1]
            assert len(call_kwargs["objective"]) == 120

    def test_empty_objective_fallback(self) -> None:
        with patch(
            "app.core.channel_bridge.goal_terminal_notifier.channel_t",
        ) as mock_t:
            mock_t.return_value = "msg"
            from app.core.channel_bridge.goal_terminal_notifier import _format_goal_notification

            _format_goal_notification(
                _goal_event_data(objective=""),
                "complete",
                "",
                "en",
            )
            call_kwargs = mock_t.call_args[1]
            assert call_kwargs["objective"] == "goal"

    def test_zero_duration(self) -> None:
        with patch(
            "app.core.channel_bridge.goal_terminal_notifier.channel_t",
        ) as mock_t:
            mock_t.return_value = "msg"
            from app.core.channel_bridge.goal_terminal_notifier import _format_goal_notification

            _format_goal_notification(
                _goal_event_data(execution_duration_s=0),
                "complete",
                "quick goal",
                "en",
            )
            call_kwargs = mock_t.call_args[1]
            assert call_kwargs["duration"] == 0
