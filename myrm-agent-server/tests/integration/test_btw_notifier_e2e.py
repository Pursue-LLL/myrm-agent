"""Integration test: _emit_btw_done → real PubSubBus → BtwTaskNotifier → channel.send.

Uses real PubSubBus (no mock on pub/sub path) and a fake channel adapter to
capture the OutboundMessage that BtwTaskNotifier delivers.
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from app.channels.reliability.retry import RetryConfig
from app.channels.types.status import ChannelStatus
from app.services.event.app_event_bus import AppEvent, AppEventType, ServerEventBus

from myrm_agent_harness.infra.pubsub.event_bus import PubSubBus


def _fake_channel(captured: list[object]) -> MagicMock:
    """Build a fake channel adapter that records sent messages."""
    ch = MagicMock()
    ch.status = ChannelStatus.RUNNING
    ch.retry_config = RetryConfig(max_retries=1, base_delay=0.01, max_delay=0.01, jitter=0)
    ch.should_retry = lambda _exc: False
    ch.extract_retry_after = lambda _exc: None
    ch.activity = MagicMock()

    async def _send(msg: object) -> None:
        captured.append(msg)

    ch.send = _send
    return ch


@pytest.mark.asyncio
async def test_emit_to_notifier_full_chain() -> None:
    """Publish BACKGROUND_TASK_DONE on real PubSubBus → BtwTaskNotifier delivers."""
    from app.core.channel_bridge.btw_notifier import BtwTaskNotifier

    bus: ServerEventBus = PubSubBus()
    notifier = BtwTaskNotifier(bus)
    await notifier.start()

    captured: list[object] = []
    fake_ch = _fake_channel(captured)

    mock_gateway = MagicMock()
    mock_gateway.bus.channels.get.return_value = fake_ch

    from unittest.mock import patch

    with (
        patch("app.core.channel_bridge.channel_gateway", mock_gateway),
        patch("app.channels.core.bus.downgrade_components", side_effect=lambda m, c: m),
    ):
        bus.publish(AppEvent(
            event_type=AppEventType.BACKGROUND_TASK_DONE,
            data={
                "task_id": "t-e2e",
                "status": "completed",
                "title": "E2E report",
                "result": "All good",
                "channel": "test-ch",
                "chat_id": "chat-e2e",
                "thread_id": "th-e2e",
                "user_id": "u-e2e",
                "locale": "en",
            },
        ))

        await asyncio.sleep(0.2)

    await notifier.stop()

    assert len(captured) == 1
    msg = captured[0]
    assert msg.channel == "test-ch"
    assert msg.recipient_id == "chat-e2e"
    assert msg.user_id == "u-e2e"
    assert "E2E report" in msg.content
    assert msg.metadata["thread_id"] == "th-e2e"


@pytest.mark.asyncio
async def test_emit_btw_done_to_notifier_failed_task() -> None:
    """Publish a failed BACKGROUND_TASK_DONE → notifier delivers failure message."""
    from app.core.channel_bridge.btw_notifier import BtwTaskNotifier

    bus: ServerEventBus = PubSubBus()
    notifier = BtwTaskNotifier(bus)
    await notifier.start()

    captured: list[object] = []
    fake_ch = _fake_channel(captured)

    mock_gateway = MagicMock()
    mock_gateway.bus.channels.get.return_value = fake_ch

    from unittest.mock import patch

    with (
        patch("app.core.channel_bridge.channel_gateway", mock_gateway),
        patch("app.channels.core.bus.downgrade_components", side_effect=lambda m, c: m),
    ):
        bus.publish(AppEvent(
            event_type=AppEventType.BACKGROUND_TASK_DONE,
            data={
                "task_id": "t-fail",
                "status": "failed",
                "title": "Broken task",
                "result": "Connection timeout",
                "channel": "test-ch",
                "chat_id": "chat-fail",
                "thread_id": "",
                "user_id": "u-fail",
                "locale": "zh-CN",
            },
        ))

        await asyncio.sleep(0.2)

    await notifier.stop()

    assert len(captured) == 1
    msg = captured[0]
    assert msg.channel == "test-ch"
    assert msg.recipient_id == "chat-fail"
    assert msg.metadata is None


@pytest.mark.asyncio
async def test_emit_btw_done_callback_publishes_to_bus() -> None:
    """_emit_btw_done on real PubSubBus → event arrives on subscriber queue."""
    from app.services.kanban.service import _emit_btw_done

    bus: ServerEventBus = PubSubBus()
    queue = bus.subscribe()

    task = MagicMock()
    task.task_id = "t-cb"
    task.title = "Callback test"
    task.result = "OK"
    task.error = ""
    task.metadata = {
        "background_source": "btw",
        "channel": "slack",
        "chat_id": "ch-cb",
        "thread_id": "th-cb",
        "user_id": "uid-cb",
        "locale": "en",
    }

    from unittest.mock import patch

    with patch("app.services.kanban.event_publisher.get_event_bus", return_value=bus):
        _emit_btw_done("task_completed", task)

    event = queue.get_nowait()
    assert event.event_type == AppEventType.BACKGROUND_TASK_DONE
    assert event.data["task_id"] == "t-cb"
    assert event.data["channel"] == "slack"
    assert event.data["status"] == "completed"


@pytest.mark.asyncio
async def test_notifier_ignores_unrelated_events() -> None:
    """BtwTaskNotifier skips non-BACKGROUND_TASK_DONE events."""
    from app.core.channel_bridge.btw_notifier import BtwTaskNotifier

    bus: ServerEventBus = PubSubBus()
    notifier = BtwTaskNotifier(bus)
    await notifier.start()

    captured: list[object] = []
    fake_ch = _fake_channel(captured)

    mock_gateway = MagicMock()
    mock_gateway.bus.channels.get.return_value = fake_ch

    from unittest.mock import patch

    with (
        patch("app.core.channel_bridge.channel_gateway", mock_gateway),
        patch("app.channels.core.bus.downgrade_components", side_effect=lambda m, c: m),
    ):
        bus.publish(AppEvent(
            event_type=AppEventType.KANBAN_TASK_UPDATED,
            data={"task_id": "ignored"},
        ))

        await asyncio.sleep(0.15)

    await notifier.stop()
    assert len(captured) == 0


@pytest.mark.asyncio
async def test_notifier_skips_disabled_channel() -> None:
    """BtwTaskNotifier skips delivery when channel status is DISABLED."""
    from app.core.channel_bridge.btw_notifier import BtwTaskNotifier

    bus: ServerEventBus = PubSubBus()
    notifier = BtwTaskNotifier(bus)
    await notifier.start()

    ch = MagicMock()
    ch.status = ChannelStatus.DISABLED
    ch.send = MagicMock()

    mock_gateway = MagicMock()
    mock_gateway.bus.channels.get.return_value = ch

    from unittest.mock import patch

    with patch("app.core.channel_bridge.channel_gateway", mock_gateway):
        bus.publish(AppEvent(
            event_type=AppEventType.BACKGROUND_TASK_DONE,
            data={
                "task_id": "t-dis",
                "status": "completed",
                "title": "Disabled ch",
                "result": "x",
                "channel": "off-ch",
                "chat_id": "c-dis",
                "thread_id": "",
                "user_id": "",
                "locale": "en",
            },
        ))

        await asyncio.sleep(0.15)

    await notifier.stop()
    ch.send.assert_not_called()


@pytest.mark.asyncio
async def test_full_chain_emit_callback_to_notifier() -> None:
    """End-to-end: _emit_btw_done callback → real PubSubBus → BtwTaskNotifier → channel.send."""
    from app.core.channel_bridge.btw_notifier import BtwTaskNotifier
    from app.services.kanban.service import _emit_btw_done

    bus: ServerEventBus = PubSubBus()
    notifier = BtwTaskNotifier(bus)
    await notifier.start()

    captured: list[object] = []
    fake_ch = _fake_channel(captured)

    mock_gateway = MagicMock()
    mock_gateway.bus.channels.get.return_value = fake_ch

    task = MagicMock()
    task.task_id = "t-chain"
    task.title = "Full chain"
    task.result = "Completed via callback"
    task.error = ""
    task.metadata = {
        "background_source": "btw",
        "channel": "chain-ch",
        "chat_id": "ch-chain",
        "thread_id": "th-chain",
        "user_id": "uid-chain",
        "locale": "en",
    }

    from unittest.mock import patch

    with (
        patch("app.services.kanban.event_publisher.get_event_bus", return_value=bus),
        patch("app.core.channel_bridge.channel_gateway", mock_gateway),
        patch("app.channels.core.bus.downgrade_components", side_effect=lambda m, c: m),
    ):
        _emit_btw_done("task_completed", task)
        await asyncio.sleep(0.2)

    await notifier.stop()

    assert len(captured) == 1
    msg = captured[0]
    assert msg.channel == "chain-ch"
    assert msg.recipient_id == "ch-chain"
    assert msg.user_id == "uid-chain"
    assert msg.metadata["thread_id"] == "th-chain"


@pytest.mark.asyncio
async def test_concurrent_events_all_delivered() -> None:
    """Multiple events published rapidly are all delivered."""
    from app.core.channel_bridge.btw_notifier import BtwTaskNotifier

    bus: ServerEventBus = PubSubBus()
    notifier = BtwTaskNotifier(bus)
    await notifier.start()

    captured: list[object] = []
    fake_ch = _fake_channel(captured)

    mock_gateway = MagicMock()
    mock_gateway.bus.channels.get.return_value = fake_ch

    from unittest.mock import patch

    with (
        patch("app.core.channel_bridge.channel_gateway", mock_gateway),
        patch("app.channels.core.bus.downgrade_components", side_effect=lambda m, c: m),
    ):
        for i in range(5):
            bus.publish(AppEvent(
                event_type=AppEventType.BACKGROUND_TASK_DONE,
                data={
                    "task_id": f"t-{i}",
                    "status": "completed",
                    "title": f"Task {i}",
                    "result": f"Result {i}",
                    "channel": "batch-ch",
                    "chat_id": f"chat-{i}",
                    "thread_id": "",
                    "user_id": "u-batch",
                    "locale": "en",
                },
            ))

        await asyncio.sleep(0.5)

    await notifier.stop()
    assert len(captured) == 5


@pytest.mark.asyncio
async def test_send_failure_does_not_crash_notifier() -> None:
    """channel.send raising does not crash the notifier loop."""
    from app.core.channel_bridge.btw_notifier import BtwTaskNotifier

    bus: ServerEventBus = PubSubBus()
    notifier = BtwTaskNotifier(bus)
    await notifier.start()

    fail_ch = MagicMock()
    fail_ch.status = ChannelStatus.RUNNING
    fail_ch.retry_config = RetryConfig(max_retries=1, base_delay=0.01, max_delay=0.01, jitter=0)
    fail_ch.should_retry = lambda _exc: False
    fail_ch.extract_retry_after = lambda _exc: None
    fail_ch.activity = MagicMock()

    async def _fail_send(_msg: object) -> None:
        raise ConnectionError("network down")

    fail_ch.send = _fail_send

    captured_after: list[object] = []
    ok_ch = _fake_channel(captured_after)

    mock_gateway = MagicMock()

    def _get_channel(name: str) -> MagicMock | None:
        if name == "fail-ch":
            return fail_ch
        if name == "ok-ch":
            return ok_ch
        return None

    mock_gateway.bus.channels.get.side_effect = _get_channel

    from unittest.mock import patch

    with (
        patch("app.core.channel_bridge.channel_gateway", mock_gateway),
        patch("app.channels.core.bus.downgrade_components", side_effect=lambda m, c: m),
    ):
        bus.publish(AppEvent(
            event_type=AppEventType.BACKGROUND_TASK_DONE,
            data={
                "task_id": "t-fail",
                "status": "completed",
                "title": "Will fail",
                "result": "",
                "channel": "fail-ch",
                "chat_id": "c1",
                "thread_id": "",
                "user_id": "",
                "locale": "en",
            },
        ))

        await asyncio.sleep(0.2)

        bus.publish(AppEvent(
            event_type=AppEventType.BACKGROUND_TASK_DONE,
            data={
                "task_id": "t-ok",
                "status": "completed",
                "title": "Will succeed",
                "result": "ok",
                "channel": "ok-ch",
                "chat_id": "c2",
                "thread_id": "",
                "user_id": "",
                "locale": "en",
            },
        ))

        await asyncio.sleep(0.2)

    await notifier.stop()

    fail_ch.activity.record_error.assert_called_once()
    assert len(captured_after) == 1
