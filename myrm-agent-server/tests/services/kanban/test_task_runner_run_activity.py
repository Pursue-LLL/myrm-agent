"""KanbanTaskRunner reports each task as in flight while its agent executes."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from myrm_agent_harness.toolkits.kanban.types import KanbanTask, TaskPriority, TaskStatus

from app.core.agent.run_activity import active_background_agent_runs
from app.services.kanban.task_runner import KanbanTaskRunner

_RUNNER = "app.services.kanban.task_runner.runner"


def _task() -> KanbanTask:
    return KanbanTask(
        task_id="task-1",
        board_id="b1",
        title="Weekly digest",
        status=TaskStatus.READY,
        priority=TaskPriority.NORMAL,
    )


async def _run(runner: KanbanTaskRunner) -> object:
    with (
        patch(f"{_RUNNER}.build_task_context", new=AsyncMock(return_value="ctx")),
        patch(f"{_RUNNER}.resolve_agent_profile", new=AsyncMock(return_value=None)),
        patch(f"{_RUNNER}.resolve_workspace", new=AsyncMock(return_value=None)),
        patch(f"{_RUNNER}.build_multimodal_query", new=AsyncMock(return_value="query")),
        patch.object(runner, "_resolve_run_outcome", new=AsyncMock(return_value=(True, "done"))),
    ):
        return await runner.run(_task())


@pytest.mark.asyncio
async def test_task_counts_as_in_flight_only_while_the_agent_executes() -> None:
    runner = KanbanTaskRunner(AsyncMock())
    observed: list[int] = []

    async def execute_agent(*_args: object, **_kwargs: object) -> str:
        observed.append(active_background_agent_runs())
        return "output"

    with patch.object(runner, "_execute_agent", new=execute_agent):
        await _run(runner)

    assert observed == [1]
    assert active_background_agent_runs() == 0


@pytest.mark.asyncio
async def test_count_is_released_when_the_agent_fails() -> None:
    runner = KanbanTaskRunner(AsyncMock())

    with patch.object(runner, "_execute_agent", new=AsyncMock(side_effect=RuntimeError("agent crashed"))):
        result = await _run(runner)

    assert result == (False, "agent crashed")
    assert active_background_agent_runs() == 0
