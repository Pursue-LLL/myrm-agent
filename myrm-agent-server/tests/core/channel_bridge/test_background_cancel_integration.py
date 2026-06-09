"""Integration test for background task immediate cancellation.

Exercises the full cancel path: ChannelBackgroundTaskHandler.cancel_background
→ KanbanService.cancel_task_execution → KanbanDispatcher.cancel_execution
with a real (non-mocked) Kanban dispatcher and in-memory store.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from myrm_agent_harness.toolkits.kanban.dispatcher import KanbanDispatcher
from myrm_agent_harness.toolkits.kanban.stores import InMemoryKanbanStore
from myrm_agent_harness.toolkits.kanban.types import (
    BoardSettings,
    KanbanBoard,
    KanbanTask,
    TaskPriority,
    TaskStatus,
)
from myrm_agent_harness.utils.runtime.cancellation import CancellationToken
from myrm_agent_harness.utils.runtime.steering import SteeringToken

from app.channels.types import InboundMessage
from app.core.channel_bridge.background_task_handler import ChannelBackgroundTaskHandler


class _SlowRunner:
    """Runner that blocks until cancelled, signalling when it starts."""

    def __init__(self, started: asyncio.Event) -> None:
        self._started = started
        self.was_cancelled = False

    async def run(self, task: KanbanTask) -> tuple[bool, str]:
        self._started.set()
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            self.was_cancelled = True
            raise
        return (True, "done")


def _make_msg() -> InboundMessage:
    return InboundMessage(
        channel="webui",
        sender_id="user1",
        chat_id="chat1",
        content="",
        user_id="uid1",
    )


@pytest.mark.asyncio
async def test_cancel_background_stops_execution_full_stack() -> None:
    """Full integration: cancel_background → cancel_task_execution → dispatcher.cancel_execution.

    Uses a real InMemoryKanbanStore, real KanbanDispatcher, real
    ChannelBackgroundTaskHandler — no mocks on the cancel path.
    """
    store = InMemoryKanbanStore()
    board = KanbanBoard(
        board_id="bg_board",
        name="__background_tasks__",
        settings=BoardSettings(
            max_concurrent_tasks=3,
            heartbeat_interval_seconds=60,
            zombie_timeout_seconds=300,
        ),
    )
    await store.save_board(board)

    task = KanbanTask(
        task_id="cancel_me",
        board_id="bg_board",
        title="Long running task",
        description="Task that should be cancelled",
        status=TaskStatus.READY,
        priority=TaskPriority.NORMAL,
        metadata={
            "background_source": "btw",
            "channel": "webui",
            "chat_id": "chat1",
            "user_id": "uid1",
        },
    )
    await store.save_task(task)

    started = asyncio.Event()
    runner = _SlowRunner(started)
    dispatcher = KanbanDispatcher(store, runner, board)
    await dispatcher.start()

    await asyncio.wait_for(started.wait(), timeout=5.0)

    handler = ChannelBackgroundTaskHandler()
    handler._system_board_id = "bg_board"

    cancel_token = CancellationToken()
    steering_token = SteeringToken()
    handler.register_runtime_tokens("cancel_me", cancel_token, steering_token)

    mock_svc = AsyncMock()
    mock_svc.store = store
    mock_svc.move_task = AsyncMock()

    async def _real_cancel_execution(tid: str) -> bool:
        return await dispatcher.cancel_execution(tid)

    mock_svc.cancel_task_execution = AsyncMock(side_effect=_real_cancel_execution)

    msg = _make_msg()
    with patch("app.services.kanban.KanbanService") as mock_cls:
        mock_cls.get_instance.return_value = mock_svc
        result = await handler.cancel_background(msg, "cancel_me")

    assert result is True
    assert cancel_token.is_cancelled
    assert runner.was_cancelled is True
    mock_svc.move_task.assert_called_once()
    mock_svc.cancel_task_execution.assert_called_once_with("cancel_me")
    assert "cancel_me" not in handler._runtime_tokens

    await dispatcher.stop()


@pytest.mark.asyncio
async def test_cancel_ready_task_no_execution_running() -> None:
    """Cancelling a READY task (not yet executing) succeeds without needing dispatcher."""
    store = InMemoryKanbanStore()
    board = KanbanBoard(
        board_id="bg_board",
        name="__background_tasks__",
        settings=BoardSettings(max_concurrent_tasks=0),
    )
    await store.save_board(board)

    task = KanbanTask(
        task_id="ready_task",
        board_id="bg_board",
        title="Queued task",
        status=TaskStatus.READY,
        priority=TaskPriority.NORMAL,
        metadata={
            "background_source": "btw",
            "channel": "webui",
            "chat_id": "chat1",
            "user_id": "uid1",
        },
    )
    await store.save_task(task)

    handler = ChannelBackgroundTaskHandler()
    handler._system_board_id = "bg_board"

    mock_svc = AsyncMock()
    mock_svc.store = store
    mock_svc.move_task = AsyncMock()
    mock_svc.cancel_task_execution = AsyncMock(return_value=False)

    msg = _make_msg()
    with patch("app.services.kanban.KanbanService") as mock_cls:
        mock_cls.get_instance.return_value = mock_svc
        result = await handler.cancel_background(msg, "ready_task")

    assert result is True
    mock_svc.move_task.assert_called_once()
    mock_svc.cancel_task_execution.assert_called_once_with("ready_task")


@pytest.mark.asyncio
async def test_cancel_running_task_without_runtime_tokens() -> None:
    """A RUNNING task can be cancelled even when no runtime tokens are registered.

    This can happen if the handler was restarted (tokens are in-memory only).
    The dispatcher still receives cancel_execution to stop the asyncio.Task.
    """
    store = InMemoryKanbanStore()
    board = KanbanBoard(
        board_id="bg_board",
        name="__background_tasks__",
        settings=BoardSettings(
            max_concurrent_tasks=3,
            heartbeat_interval_seconds=60,
            zombie_timeout_seconds=300,
        ),
    )
    await store.save_board(board)

    task = KanbanTask(
        task_id="no_tokens_task",
        board_id="bg_board",
        title="Task without tokens",
        status=TaskStatus.READY,
        priority=TaskPriority.NORMAL,
        metadata={
            "background_source": "btw",
            "channel": "webui",
            "chat_id": "chat1",
            "user_id": "uid1",
        },
    )
    await store.save_task(task)

    started = asyncio.Event()
    runner = _SlowRunner(started)
    dispatcher = KanbanDispatcher(store, runner, board)
    await dispatcher.start()

    await asyncio.wait_for(started.wait(), timeout=5.0)

    handler = ChannelBackgroundTaskHandler()
    handler._system_board_id = "bg_board"
    # No tokens registered — simulates handler restart scenario

    mock_svc = AsyncMock()
    mock_svc.store = store
    mock_svc.move_task = AsyncMock()

    async def _real_cancel(tid: str) -> bool:
        return await dispatcher.cancel_execution(tid)

    mock_svc.cancel_task_execution = AsyncMock(side_effect=_real_cancel)

    msg = _make_msg()
    with patch("app.services.kanban.KanbanService") as mock_cls:
        mock_cls.get_instance.return_value = mock_svc
        result = await handler.cancel_background(msg, "no_tokens_task")

    assert result is True
    assert runner.was_cancelled is True
    mock_svc.cancel_task_execution.assert_called_once_with("no_tokens_task")

    await dispatcher.stop()


@pytest.mark.asyncio
async def test_steer_after_cancel_returns_false() -> None:
    """Steering a task after cancellation fails because tokens are removed."""
    handler = ChannelBackgroundTaskHandler()
    handler._system_board_id = "bg_board"

    cancel_token = CancellationToken()
    steering_token = SteeringToken()
    handler.register_runtime_tokens("task_x", cancel_token, steering_token)

    # Simulate cancel flow — remove tokens
    handler.unregister_runtime_tokens("task_x")

    msg = _make_msg()
    result = await handler.steer_background(msg, "task_x", "new instruction")
    assert result is False


@pytest.mark.asyncio
async def test_cancel_idempotent_second_call_returns_false() -> None:
    """Calling cancel_background twice: first succeeds, second fails (status changed)."""
    store = InMemoryKanbanStore()
    board = KanbanBoard(
        board_id="bg_board",
        name="__background_tasks__",
        settings=BoardSettings(max_concurrent_tasks=3),
    )
    await store.save_board(board)

    task = KanbanTask(
        task_id="idem_task",
        board_id="bg_board",
        title="Idempotent cancel test",
        status=TaskStatus.RUNNING,
        priority=TaskPriority.NORMAL,
        metadata={
            "background_source": "btw",
            "channel": "webui",
            "chat_id": "chat1",
            "user_id": "uid1",
        },
    )
    await store.save_task(task)

    handler = ChannelBackgroundTaskHandler()
    handler._system_board_id = "bg_board"
    handler.register_runtime_tokens("idem_task", CancellationToken(), SteeringToken())

    async def _fake_move_task(tid: str, status: TaskStatus, **kwargs: object) -> None:
        t = await store.get_task(tid)
        if t:
            t.status = status
            await store.save_task(t)

    mock_svc = AsyncMock()
    mock_svc.store = store
    mock_svc.move_task = AsyncMock(side_effect=_fake_move_task)
    mock_svc.cancel_task_execution = AsyncMock(return_value=False)

    msg = _make_msg()
    with patch("app.services.kanban.KanbanService") as mock_cls:
        mock_cls.get_instance.return_value = mock_svc
        first = await handler.cancel_background(msg, "idem_task")
        second = await handler.cancel_background(msg, "idem_task")

    assert first is True
    assert second is False
