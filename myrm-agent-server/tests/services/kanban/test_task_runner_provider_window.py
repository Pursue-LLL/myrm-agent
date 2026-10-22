"""Provider usage-limit rescheduling of kanban tasks through the real dispatcher."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from myrm_agent_harness.agent.goals.manager import GoalManager
from myrm_agent_harness.agent.goals.types import GoalStatus
from myrm_agent_harness.agent.goals.wait_provider_window import park_goal_for_provider_window
from myrm_agent_harness.toolkits.kanban.dispatcher import KanbanDispatcher
from myrm_agent_harness.toolkits.kanban.stores import InMemoryKanbanStore
from myrm_agent_harness.toolkits.kanban.types import (
    BlockKind,
    BoardSettings,
    KanbanBoard,
    KanbanTask,
    TaskExecutionResult,
    TaskPriority,
    TaskStatus,
)
from myrm_agent_harness.toolkits.llms.errors import FailoverReason, MyrmLLMError
from myrm_agent_harness.toolkits.llms.errors.provider_window import ProviderWindowHint, WindowSource
from myrm_agent_harness.toolkits.storage.local import LocalStorageBackend

from app.services.kanban.task_runner import KanbanTaskRunner

_RUNNER = "app.services.kanban.task_runner.runner"


def _limit_error(cooldown_ms: int | None) -> MyrmLLMError:
    context = {"cooldown_remaining_ms": cooldown_ms} if cooldown_ms is not None else None
    return MyrmLLMError(error_code=FailoverReason.RATE_LIMIT, default_msg="usage limit reached", context=context)


def _task() -> KanbanTask:
    return KanbanTask(
        task_id="task-1",
        board_id="b1",
        title="Weekly digest",
        status=TaskStatus.READY,
        priority=TaskPriority.NORMAL,
    )


async def _run(runner: KanbanTaskRunner, task: KanbanTask) -> tuple[bool, str] | TaskExecutionResult:
    with (
        patch(f"{_RUNNER}.build_task_context", new=AsyncMock(return_value="ctx")),
        patch(f"{_RUNNER}.resolve_agent_profile", new=AsyncMock(return_value=None)),
        patch(f"{_RUNNER}.resolve_workspace", new=AsyncMock(return_value=None)),
        patch(f"{_RUNNER}.build_multimodal_query", new=AsyncMock(return_value="query")),
    ):
        return await runner.run(task)


@pytest.mark.asyncio
async def test_usage_limit_becomes_a_scheduled_block_at_the_provider_boundary() -> None:
    runner = KanbanTaskRunner(AsyncMock())
    before = datetime.now(UTC)

    with patch.object(runner, "_execute_agent", new=AsyncMock(side_effect=_limit_error(2 * 3600 * 1000))):
        result = await _run(runner, _task())

    assert isinstance(result, TaskExecutionResult)
    assert result.is_blocked
    assert result.block_kind is BlockKind.SCHEDULED
    assert result.scheduled_until is not None
    assert before + timedelta(hours=2) <= result.scheduled_until <= datetime.now(UTC) + timedelta(hours=2)


@pytest.mark.asyncio
@pytest.mark.parametrize("cooldown_ms", [None, 25 * 3600 * 1000])
async def test_without_a_waitable_boundary_the_failure_path_is_unchanged(cooldown_ms: int | None) -> None:
    runner = KanbanTaskRunner(AsyncMock())

    with patch.object(runner, "_execute_agent", new=AsyncMock(side_effect=_limit_error(cooldown_ms))):
        result = await _run(runner, _task())

    assert isinstance(result, tuple)
    assert result[0] is False


@pytest.mark.asyncio
async def test_dispatcher_parks_the_task_without_counting_a_failure() -> None:
    store = InMemoryKanbanStore()
    board = KanbanBoard(
        board_id="b1",
        name="Board",
        settings=BoardSettings(auto_block_after_consecutive_failures=1, heartbeat_interval_seconds=1),
    )
    await store.save_task(_task())
    runner = KanbanTaskRunner(AsyncMock())
    dispatcher = KanbanDispatcher(store, runner, board)

    with (
        patch.object(runner, "_execute_agent", new=AsyncMock(side_effect=_limit_error(3600 * 1000))),
        patch(f"{_RUNNER}.build_task_context", new=AsyncMock(return_value="ctx")),
        patch(f"{_RUNNER}.resolve_agent_profile", new=AsyncMock(return_value=None)),
        patch(f"{_RUNNER}.resolve_workspace", new=AsyncMock(return_value=None)),
        patch(f"{_RUNNER}.build_multimodal_query", new=AsyncMock(return_value="query")),
    ):
        await dispatcher.start()
        try:
            for _ in range(50):
                task = await store.get_task("task-1")
                if task is not None and task.status is TaskStatus.BLOCKED:
                    break
                await asyncio.sleep(0.1)
        finally:
            await dispatcher.stop()

    task = await store.get_task("task-1")
    assert task is not None
    assert task.status is TaskStatus.BLOCKED
    assert task.block_kind is BlockKind.SCHEDULED
    assert task.scheduled_until is not None
    assert task.scheduled_until > datetime.now(UTC) + timedelta(minutes=50)
    assert task.consecutive_failures == 0


@pytest.mark.asyncio
async def test_a_kanban_goal_is_never_parked_by_the_usage_limit_hold(tmp_path, monkeypatch) -> None:
    """The stream runs under the bare task id while the goal lives under ``kanban:<id>``.

    The hold therefore finds no goal to park, the turn fails with the typed limit error, and the task is
    rescheduled by the scheduler above instead of being woken by the chat daemon.
    """
    manager = GoalManager(LocalStorageBackend(base_path=str(tmp_path)))
    monkeypatch.setattr(f"{_RUNNER}.GoalRegistry.get_or_create_provider", lambda session_id: manager)
    task = _task()
    await KanbanTaskRunner(AsyncMock())._setup_goal_provider(task)
    now = datetime.now(UTC).timestamp()
    hint = ProviderWindowHint(reset_at=now + 3600, wait_s=3600, source=WindowSource.ANTHROPIC_UNIFIED, quota_window=True)

    parked = await park_goal_for_provider_window(manager, task.task_id, hint)

    assert parked is None
    goal = await manager.get_latest_goal(f"kanban:{task.task_id}")
    assert goal is not None
    assert goal.status is GoalStatus.ACTIVE
