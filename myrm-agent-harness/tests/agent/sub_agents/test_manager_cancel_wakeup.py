"""A cancelled child must not wake the parent; every other terminal status still does.

A user Stop cancels detached children (``cancel_all(include_detached=True)``). If their cleanup
woke the parent, the server would start a new autonomous run right after the user pressed Stop.
These tests drive the real ``SubagentManager`` cleanup path.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from unittest.mock import MagicMock, patch

import pytest

from myrm_agent_harness.agent.sub_agents.manager import SubagentManager
from myrm_agent_harness.agent.sub_agents.types import (
    CancellationStrategy,
    SubagentConfig,
    SubAgentResult,
    SubAgentStatus,
)

ChildBody = Callable[[], Awaitable[SubAgentResult]]


class _Parent:
    """Minimal parent agent: only the surface ``_cleanup_child`` touches."""

    session_id = "wakeup-test-session"

    def __init__(self) -> None:
        self.woken: list[SubAgentResult] = []

    async def trigger_async_wakeup(self, result: SubAgentResult) -> None:
        self.woken.append(result)


def _result(task_id: str, status: SubAgentStatus) -> SubAgentResult:
    return SubAgentResult(
        success=status is SubAgentStatus.COMPLETED,
        task_id=task_id,
        agent_type="researcher",
        result="done" if status is SubAgentStatus.COMPLETED else None,
        error=None if status is SubAgentStatus.COMPLETED else status.value,
        completed_at=time.time(),
        status=status,
    )


def _manager() -> tuple[SubagentManager, _Parent]:
    parent = _Parent()
    with patch("myrm_agent_harness.agent.hooks.graceful_shutdown.get_shutdown_manager") as shutdown:
        shutdown.return_value = MagicMock()
        return SubagentManager(parent_agent=parent), parent  # type: ignore[arg-type]


async def _start_detached(
    manager: SubagentManager,
    task_id: str,
    body: ChildBody,
    strategy: CancellationStrategy | None = None,
) -> asyncio.Task[SubAgentResult]:
    task = asyncio.create_task(body())
    manager._children[task_id] = task
    manager._children_detached[task_id] = True
    manager._children_types[task_id] = "researcher"
    manager._children_descriptions[task_id] = "long job"
    if strategy is not None:
        manager._children_configs[task_id] = SubagentConfig(
            system_prompt="s",
            cancellation_strategy=strategy,
            graceful_cancel_timeout_seconds=0.05,
        )
    task.add_done_callback(lambda done: manager._cleanup_child(task_id, done))
    await asyncio.sleep(0)
    return task


async def _settle(manager: SubagentManager, task: asyncio.Task[SubAgentResult]) -> None:
    await asyncio.gather(task, return_exceptions=True)
    await asyncio.sleep(0)
    pending = list(manager._background_tasks)
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)


async def _sleep_forever() -> SubAgentResult:
    await asyncio.sleep(3600)
    raise AssertionError("unreachable")


@pytest.mark.asyncio
@pytest.mark.parametrize("strategy", [None, CancellationStrategy.IMMEDIATE, CancellationStrategy.GRACEFUL])
async def test_cancelled_child_does_not_wake_parent(strategy: CancellationStrategy | None) -> None:
    manager, parent = _manager()
    task_id = f"cancel-{strategy}"
    task = await _start_detached(manager, task_id, _sleep_forever, strategy)

    assert manager.cancel_all(include_detached=True) == 1
    await _settle(manager, task)

    assert manager._children_results[task_id].status is SubAgentStatus.CANCELLED
    assert parent.woken == []


@pytest.mark.asyncio
async def test_child_that_reports_cancelled_does_not_wake_parent() -> None:
    """The real executor catches the cancellation and returns a CANCELLED result."""
    manager, parent = _manager()
    task_id = "cancel-cooperative"

    async def cooperative() -> SubAgentResult:
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            return _result(task_id, SubAgentStatus.CANCELLED)
        raise AssertionError("unreachable")

    task = await _start_detached(manager, task_id, cooperative, CancellationStrategy.IMMEDIATE)
    manager.cancel_all(include_detached=True)
    await _settle(manager, task)

    assert manager._children_results[task_id].status is SubAgentStatus.CANCELLED
    assert parent.woken == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status",
    [
        SubAgentStatus.COMPLETED,
        SubAgentStatus.FAILED,
        SubAgentStatus.TIMED_OUT,
        SubAgentStatus.CANCELLED_BY_BUDGET,
    ],
)
async def test_other_terminal_statuses_still_wake_parent(status: SubAgentStatus) -> None:
    manager, parent = _manager()
    task_id = f"finish-{status.value}"

    async def finish() -> SubAgentResult:
        return _result(task_id, status)

    task = await _start_detached(manager, task_id, finish)
    await _settle(manager, task)

    assert [woken.status for woken in parent.woken] == [status]


@pytest.mark.asyncio
async def test_child_that_raises_still_wakes_parent() -> None:
    manager, parent = _manager()
    task_id = "finish-raises"

    async def boom() -> SubAgentResult:
        raise RuntimeError("tool crashed")

    task = await _start_detached(manager, task_id, boom)
    await _settle(manager, task)

    assert [woken.status for woken in parent.woken] == [SubAgentStatus.FAILED]
