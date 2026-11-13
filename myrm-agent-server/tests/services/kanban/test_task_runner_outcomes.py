"""The completion gate that turns a finished run into the task's verdict."""

from unittest.mock import AsyncMock

import pytest
from myrm_agent_harness.toolkits.kanban.types import KanbanTask

from app.services.kanban.task_runner import KanbanTaskRunner


class TestResolveRunOutcome:
    """Completion gate enforcement in KanbanTaskRunner._resolve_run_outcome."""

    @pytest.mark.asyncio
    async def test_blocked_task_returns_failure(self) -> None:
        from myrm_agent_harness.toolkits.kanban.types import (
            TaskExecutionOutcome,
            TaskExecutionResult,
            TaskStatus,
        )

        task = KanbanTask(
            task_id="t-block",
            board_id="b1",
            title="Blocked",
            status=TaskStatus.BLOCKED,
            blocked_reason="Need API key",
        )
        mock_store = AsyncMock()
        mock_store.get_task.return_value = task
        runner = KanbanTaskRunner(mock_store)

        outcome = await runner._resolve_run_outcome("t-block", (True, "ignored"))

        assert isinstance(outcome, TaskExecutionResult)
        assert outcome.outcome == TaskExecutionOutcome.BLOCKED
        assert outcome.message == "Need API key"

    @pytest.mark.asyncio
    async def test_completion_intent_returns_summary(self) -> None:
        task = KanbanTask(
            task_id="t-intent",
            board_id="b1",
            title="Done",
            metadata={"completion_intent": True},
            result="Finished refactor",
        )
        mock_store = AsyncMock()
        mock_store.get_task.return_value = task
        runner = KanbanTaskRunner(mock_store)

        ok, msg = await runner._resolve_run_outcome("t-intent", (True, "stream text"))

        assert ok is True
        assert msg == "Finished refactor"

    @pytest.mark.asyncio
    async def test_success_without_intent_is_protocol_violation(self) -> None:
        from app.services.kanban.task_runner.outcomes import PROTOCOL_VIOLATION_MSG

        task = KanbanTask(
            task_id="t-violation",
            board_id="b1",
            title="Incomplete",
        )
        mock_store = AsyncMock()
        mock_store.get_task.return_value = task
        runner = KanbanTaskRunner(mock_store)

        ok, msg = await runner._resolve_run_outcome("t-violation", (True, "forgot kanban_complete"))

        assert ok is False
        assert msg == PROTOCOL_VIOLATION_MSG

    @pytest.mark.asyncio
    async def test_agent_failure_passthrough(self) -> None:
        task = KanbanTask(task_id="t-fail", board_id="b1", title="Fail")
        mock_store = AsyncMock()
        mock_store.get_task.return_value = task
        runner = KanbanTaskRunner(mock_store)

        ok, msg = await runner._resolve_run_outcome("t-fail", (False, "agent crashed"))

        assert ok is False
        assert msg == "agent crashed"

    @pytest.mark.asyncio
    async def test_missing_task_after_execution(self) -> None:
        mock_store = AsyncMock()
        mock_store.get_task.return_value = None
        runner = KanbanTaskRunner(mock_store)

        ok, msg = await runner._resolve_run_outcome("missing", (True, "x"))

        assert ok is False
        assert msg == "Task not found after execution"
