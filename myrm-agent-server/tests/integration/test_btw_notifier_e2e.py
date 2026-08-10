"""Integration test: _emit_btw_done → real PubSubBus → BtwTaskNotifier → channel.send.

Uses real PubSubBus (no mock on pub/sub path) and a fake channel adapter to
capture the OutboundMessage that BtwTaskNotifier delivers. Shared test
infrastructure lives in ``_btw_notifier_testkit``.
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest
from _btw_notifier_testkit import (
    _background_event,
    _btw_task,
    _fake_channel,
    _FakeRunner,
    _make_notifier_harness,
    _make_review_store,
    _PassVerifier,
    _patched_delivery,
    _wait_for_messages,
)
from myrm_agent_harness.infra.pubsub.event_bus import PubSubBus
from myrm_agent_harness.toolkits.kanban.dispatcher import KanbanDispatcher
from myrm_agent_harness.toolkits.kanban.types import TaskStatus

from app.channels.reliability.retry import RetryConfig
from app.channels.types.status import ChannelStatus
from app.services.event.app_event_bus import AppEvent, AppEventType, ServerEventBus


@pytest.mark.asyncio
async def test_emit_to_notifier_full_chain() -> None:
    """Publish BACKGROUND_TASK_DONE on real PubSubBus → BtwTaskNotifier delivers."""
    captured: list[object] = []
    bus, notifier, mock_gateway = await _make_notifier_harness(captured)

    with _patched_delivery(mock_gateway):
        _background_event(
            bus,
            task_id="t-e2e",
            status="completed",
            title="E2E report",
            result="All good",
            chat_id="chat-e2e",
            thread_id="th-e2e",
            user_id="u-e2e",
        )

        await _wait_for_messages(captured, 1)

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
    captured: list[object] = []
    bus, notifier, mock_gateway = await _make_notifier_harness(captured)

    with _patched_delivery(mock_gateway):
        _background_event(
            bus,
            task_id="t-fail",
            status="failed",
            title="Broken task",
            result="Connection timeout",
            chat_id="chat-fail",
            user_id="u-fail",
            locale="zh-CN",
        )

        await _wait_for_messages(captured, 1)

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

    task = _btw_task(
        "t-cb",
        "Callback test",
        "OK",
        channel="slack",
        chat_id="ch-cb",
        thread_id="th-cb",
        user_id="uid-cb",
    )

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
    captured: list[object] = []
    bus, notifier, mock_gateway = await _make_notifier_harness(captured)

    with _patched_delivery(mock_gateway):
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
    captured: list[object] = []
    bus, notifier, mock_gateway = await _make_notifier_harness(captured)

    ch = MagicMock()
    ch.status = ChannelStatus.DISABLED
    ch.send = MagicMock()
    mock_gateway.bus.channels.get.return_value = ch

    with _patched_delivery(mock_gateway):
        _background_event(
            bus,
            task_id="t-dis",
            status="completed",
            title="Disabled ch",
            result="x",
            channel="off-ch",
            chat_id="c-dis",
        )

        await asyncio.sleep(0.15)

    await notifier.stop()
    ch.send.assert_not_called()


@pytest.mark.asyncio
async def test_full_chain_emit_callback_to_notifier() -> None:
    """End-to-end: _emit_btw_done callback → real PubSubBus → BtwTaskNotifier → channel.send."""
    from app.services.kanban.service import _emit_btw_done

    captured: list[object] = []
    bus, notifier, mock_gateway = await _make_notifier_harness(captured)

    task = _btw_task(
        "t-chain",
        "Full chain",
        "Completed via callback",
        channel="chain-ch",
        chat_id="ch-chain",
        thread_id="th-chain",
        user_id="uid-chain",
    )

    with (
        _patched_delivery(mock_gateway),
        patch("app.services.kanban.event_publisher.get_event_bus", return_value=bus),
    ):
        _emit_btw_done("task_completed", task)
        await _wait_for_messages(captured, 1)

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
    captured: list[object] = []
    bus, notifier, mock_gateway = await _make_notifier_harness(captured)

    with _patched_delivery(mock_gateway):
        for i in range(5):
            _background_event(
                bus,
                task_id=f"t-{i}",
                status="completed",
                title=f"Task {i}",
                result=f"Result {i}",
                chat_id=f"chat-{i}",
                user_id="u-batch",
            )

        await _wait_for_messages(captured, 5)

    await notifier.stop()
    assert len(captured) == 5


@pytest.mark.asyncio
async def test_send_failure_does_not_crash_notifier() -> None:
    """channel.send raising does not crash the notifier loop."""
    captured_after: list[object] = []
    bus, notifier, mock_gateway = await _make_notifier_harness(captured_after)

    fail_ch = MagicMock()
    fail_ch.status = ChannelStatus.RUNNING
    fail_ch.retry_config = RetryConfig(max_retries=1, base_delay=0.01, max_delay=0.01, jitter=0)
    fail_ch.should_retry = lambda _exc: False
    fail_ch.extract_retry_after = lambda _exc: None
    fail_ch.activity = MagicMock()

    async def _fail_send(_msg: object) -> None:
        raise ConnectionError("network down")

    fail_ch.send = _fail_send

    ok_ch = _fake_channel(captured_after)

    def _get_channel(name: str) -> MagicMock | None:
        if name == "fail-ch":
            return fail_ch
        if name == "ok-ch":
            return ok_ch
        return None

    mock_gateway.bus.channels.get.side_effect = _get_channel

    with _patched_delivery(mock_gateway):
        _background_event(
            bus,
            task_id="t-fail",
            status="completed",
            title="Will fail",
            result="",
            channel="fail-ch",
            chat_id="c1",
        )

        await asyncio.sleep(0.2)

        _background_event(
            bus,
            task_id="t-ok",
            status="completed",
            title="Will succeed",
            result="ok",
            channel="ok-ch",
            chat_id="c2",
        )

        await _wait_for_messages(captured_after, 1)

    await notifier.stop()

    fail_ch.activity.record_error.assert_called_once()
    assert len(captured_after) == 1


@pytest.mark.asyncio
async def test_dispatcher_reject_task_delivers_im_notification() -> None:
    """End-to-end: KanbanDispatcher.reject_task → task_rejected → emit_task_rejected
    → real PubSubBus → BtwTaskNotifier → channel.send.

    Mirrors the callback wiring in dispatcher_lifecycle.start_dispatcher so the
    dispatcher (not fallback) path of the rejection notice is covered.
    """
    from app.services.kanban.event_publisher import emit_task_rejected

    store, board = await _make_review_store(
        "t-reject-e2e",
        {
            "background_source": "btw",
            "channel": "tg-ch",
            "chat_id": "chat-reject",
            "thread_id": None,  # private chat: no thread → must not become "None"
            "user_id": "uid-reject",
            "locale": "en",
        },
    )

    captured: list[object] = []
    bus, notifier, mock_gateway = await _make_notifier_harness(captured)

    dispatcher = KanbanDispatcher(store, _FakeRunner(), board, verifier=_PassVerifier())
    dispatcher.on_event(
        lambda event_type, t: (
            emit_task_rejected(t) if event_type == "task_rejected" else None
        )
    )

    with (
        _patched_delivery(mock_gateway),
        patch("app.services.kanban.event_publisher.get_event_bus", return_value=bus),
    ):
        rejected = await dispatcher.reject_task(
            "t-reject-e2e",
            reason="missing source citations",
            approver="bob",
        )
        await _wait_for_messages(captured, 1)

    await notifier.stop()

    assert rejected is not None
    assert rejected.status == TaskStatus.READY
    assert len(captured) == 1
    msg = captured[0]
    assert msg.channel == "tg-ch"
    assert msg.recipient_id == "chat-reject"
    assert msg.user_id == "uid-reject"
    assert msg.metadata is None  # thread_id was None → no "None" string in metadata
    assert "missing source citations" in msg.content


@pytest.mark.asyncio
async def test_dispatcher_reject_task_delivers_thread_notification() -> None:
    """Thread-aware rejection: thread_id present in metadata is preserved."""
    from app.services.kanban.event_publisher import emit_task_rejected

    store, board = await _make_review_store(
        "t-reject-thread",
        {
            "background_source": "btw",
            "channel": "slack",
            "chat_id": "chat-thread",
            "thread_id": "th-42",
            "user_id": "uid-thread",
            "locale": "zh-CN",
        },
    )

    captured: list[object] = []
    bus, notifier, mock_gateway = await _make_notifier_harness(captured)

    dispatcher = KanbanDispatcher(store, _FakeRunner(), board, verifier=_PassVerifier())
    dispatcher.on_event(
        lambda event_type, t: (
            emit_task_rejected(t) if event_type == "task_rejected" else None
        )
    )

    with (
        _patched_delivery(mock_gateway),
        patch("app.services.kanban.event_publisher.get_event_bus", return_value=bus),
    ):
        await dispatcher.reject_task(
            "t-reject-thread",
            reason="请补充数据来源",
            approver="alice",
        )
        await _wait_for_messages(captured, 1)

    await notifier.stop()

    assert len(captured) == 1
    msg = captured[0]
    assert msg.channel == "slack"
    assert msg.recipient_id == "chat-thread"
    assert msg.user_id == "uid-thread"
    assert msg.metadata == {"thread_id": "th-42"}
    assert "请补充数据来源" in msg.content


@pytest.mark.asyncio
async def test_emit_btw_done_blocked_publishes_notification() -> None:
    """/btw auto-blocked (HUMAN) → BACKGROUND_TASK_DONE with status=blocked."""
    from myrm_agent_harness.toolkits.kanban.types import BlockKind

    from app.services.kanban.event_publisher import emit_btw_done

    bus: ServerEventBus = PubSubBus()
    queue = bus.subscribe()

    task = _btw_task(
        "t-blk",
        "Blocked task",
        "partial result",
        channel="tg-ch",
        chat_id="chat-blk",
        user_id="u-blk",
    )
    task.block_kind = BlockKind.HUMAN
    task.blocked_reason = "Auto-blocked after 3 consecutive failures"

    with patch("app.services.kanban.event_publisher.get_event_bus", return_value=bus):
        emit_btw_done("task_blocked", task)

    event = queue.get_nowait()
    assert event.event_type == AppEventType.BACKGROUND_TASK_DONE
    assert event.data["status"] == "blocked"
    assert event.data["task_id"] == "t-blk"
    assert "Auto-blocked after 3 consecutive failures" in event.data["result"]


@pytest.mark.asyncio
async def test_emit_btw_done_scheduled_block_skipped() -> None:
    """Scheduled (transient backoff) blocks are not terminal → no notification."""
    from myrm_agent_harness.toolkits.kanban.types import BlockKind

    from app.services.kanban.event_publisher import emit_btw_done

    bus: ServerEventBus = PubSubBus()
    queue = bus.subscribe()

    task = _btw_task(
        "t-sched",
        "Transient task",
        "",
        channel="tg-ch",
        chat_id="chat-sched",
    )
    task.block_kind = BlockKind.SCHEDULED
    task.blocked_reason = "Transient error detected, auto-retry"

    with patch("app.services.kanban.event_publisher.get_event_bus", return_value=bus):
        emit_btw_done("task_blocked", task)

    assert queue.empty()


@pytest.mark.asyncio
async def test_blocked_btw_delivers_im_notification() -> None:
    """End-to-end: blocked /btw task → BACKGROUND_TASK_DONE(blocked) → channel.send."""
    from myrm_agent_harness.toolkits.kanban.types import BlockKind

    captured: list[object] = []
    bus, notifier, mock_gateway = await _make_notifier_harness(captured)

    with (
        _patched_delivery(mock_gateway),
        patch("app.services.kanban.event_publisher.get_event_bus", return_value=bus),
    ):
        from app.services.kanban.event_publisher import emit_btw_done

        task = _btw_task(
            "t-blk-e2e",
            "Blocked E2E",
            "",
            channel="tg-ch",
            chat_id="chat-blk-e2e",
            user_id="uid-blk",
        )
        task.block_kind = BlockKind.HUMAN
        task.blocked_reason = "Auto-blocked after 3 consecutive failures"

        emit_btw_done("task_blocked", task)
        await _wait_for_messages(captured, 1)

    await notifier.stop()

    assert len(captured) == 1
    msg = captured[0]
    assert msg.channel == "tg-ch"
    assert msg.recipient_id == "chat-blk-e2e"
    assert "Auto-blocked after 3 consecutive failures" in msg.content
    assert msg.metadata is None
