"""The guard's todo-list check, unwritten-deliverable check and forced-finish staging."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.runtime import Runtime

from myrm_agent_harness.agent.middlewares.completion.completion_guard import (
    CompletionGuard,
    reset_completion_guard,
)
from myrm_agent_harness.agent.middlewares.completion.completion_guard.checklist import (
    build_checklist,
)
from myrm_agent_harness.agent.security.guards.loop_guard import (
    CallRecord,
    SuccessLevel,
)
from tests.support.completion_guard_harness import (
    LOOP_GUARD_PATCH,
    make_state,
    reasons_of,
)


class TestCompletionGuardTodoChecklist:
    """Test the checklist's todo items integration and blocked guidance."""

    def test_build_checklist_with_blocked_and_actionable_todos(self, tmp_path: Path) -> None:
        from myrm_agent_harness.agent.meta_tools.progress.schemas import (
            TodoItem,
            TodoStatus,
            TodoStore,
        )
        from myrm_agent_harness.agent.meta_tools.progress.storage import (
            write_todos_sync_to_workspace,
        )

        store = TodoStore(
            goal="Test todo checklist",
            todos=[
                TodoItem(id="t1", content="fetch remote resource", status=TodoStatus.BLOCKED),
                TodoItem(id="t2", content="implement core logic", status=TodoStatus.IN_PROGRESS),
                TodoItem(id="t3", content="done item", status=TodoStatus.COMPLETED),
            ],
        )
        write_todos_sync_to_workspace(str(tmp_path), store)

        records = [
            CallRecord(
                tool_name="file_write_tool",
                args_hash="w1",
                args={"path": "/tmp/test.py"},
                success_level=SuccessLevel.FULL_SUCCESS,
            )
        ]
        checklist, has_critical = build_checklist(records, workspace_root=str(tmp_path))
        assert has_critical is True
        assert "CRITICAL: You have incomplete todos in your task list!" in checklist
        assert "Todo t1: fetch remote resource (Status: blocked)" in checklist
        assert "Todo t2: implement core logic (Status: in_progress)" in checklist
        assert "You MUST complete actionable todos and call `todo_write(merge=true)` before finishing." in checklist
        assert (
            "For blocked todos that cannot be completed due to external constraints, mark them as 'cancelled'"
            in checklist
        )

    def test_build_checklist_with_only_blocked_todos(self, tmp_path: Path) -> None:
        from myrm_agent_harness.agent.meta_tools.progress.schemas import (
            TodoItem,
            TodoStatus,
            TodoStore,
        )
        from myrm_agent_harness.agent.meta_tools.progress.storage import (
            write_todos_sync_to_workspace,
        )

        store = TodoStore(
            goal="Test blocked-only checklist",
            todos=[
                TodoItem(id="t1", content="external service down", status=TodoStatus.BLOCKED),
                TodoItem(id="t2", content="done item", status=TodoStatus.COMPLETED),
            ],
        )
        write_todos_sync_to_workspace(str(tmp_path), store)

        records = [
            CallRecord(
                tool_name="file_write_tool",
                args_hash="w1",
                args={"path": "/tmp/test.py"},
                success_level=SuccessLevel.FULL_SUCCESS,
            )
        ]
        checklist, has_critical = build_checklist(records, workspace_root=str(tmp_path))
        assert has_critical is True
        assert "CRITICAL: You have incomplete todos in your task list!" in checklist
        assert "Todo t1: external service down (Status: blocked)" in checklist
        # Should NOT prompt to complete actionable todos since there are none
        assert "You MUST complete actionable todos" not in checklist
        # Should prompt to mark blocked as cancelled
        assert (
            "For blocked todos that cannot be completed due to external constraints, mark them as 'cancelled'"
            in checklist
        )


class TestCompletionGuardUnwrittenDeliverablesAndAutoStaging:
    """Test unwritten deliverable gate and auto-staging integration in CompletionGuard."""

    def setup_method(self) -> None:
        self.guard = CompletionGuard(max_rejections=2)
        reset_completion_guard()

    @pytest.mark.asyncio
    async def test_blocks_completion_when_substantive_code_without_write(self, tmp_path: Path) -> None:
        code_msg = (
            "Here is the implementation:\n"
            "```python\n"
            "# filename: app/server.py\n"
            "from fastapi import FastAPI\n"
            "app = FastAPI()\n"
            "\n"
            "@app.get('/health')\n"
            "def health():\n"
            "    return {'status': 'ok'}\n"
            "```\n"
            "All done!"
        )
        state = make_state(
            [
                HumanMessage(content="Please implement the FastAPI server."),
                AIMessage(content=code_msg),
            ]
        )
        runtime = Runtime(context={"workspace_path": str(tmp_path)})

        mock_loop_guard = MagicMock()
        mock_loop_guard._window = []

        with patch(LOOP_GUARD_PATCH, return_value=mock_loop_guard):
            res = await self.guard.aafter_model(state, runtime)

        assert "Substantial unpersisted deliverables detected" in reasons_of(res).deliverable_write

    @pytest.mark.asyncio
    async def test_forced_finish_triggers_auto_staging(self, tmp_path: Path) -> None:
        code_msg = (
            "```python\n"
            "# filename: app/calc.py\n"
            "def add(a, b):\n"
            "    return a + b\n"
            "\n"
            "def sub(a, b):\n"
            "    return a - b\n"
            "```"
        )
        state = make_state(
            [
                HumanMessage(content="Create calculator"),
                AIMessage(content=code_msg),
            ]
        )
        runtime = Runtime(context={"workspace_path": str(tmp_path)})

        mock_loop_guard = MagicMock()
        mock_loop_guard._window = []

        with patch(LOOP_GUARD_PATCH, return_value=mock_loop_guard):
            # First rejection
            res1 = await self.guard.aafter_model(state, runtime)
            assert res1 is not None

            # Second rejection
            res2 = await self.guard.aafter_model(state, runtime)
            assert res2 is not None

            # Third attempt triggers max_rejections (max_rejections=2) -> forced finish
            res3 = await self.guard.aafter_model(state, runtime)
            forced = reasons_of(res3)
            assert forced.forced_finish is True
            staged = forced.staged_artifacts
            assert len(staged) == 1
            assert staged[0]["original_hint"] == "app/calc.py"

            # Verify actual file staged in sandbox workspace
            staged_dir = tmp_path / ".myrm" / "staged_artifacts"
            assert staged_dir.exists()
            staged_files = list(staged_dir.glob("*_calc.py"))
            assert len(staged_files) == 1
            assert "def add(a, b):" in staged_files[0].read_text(encoding="utf-8")

    @pytest.mark.asyncio
    async def test_pedagogical_snippet_not_blocked(self, tmp_path: Path) -> None:
        snippet_msg = (
            "Here is how quicksort works in theory:\n"
            "```python\n"
            "def qs(arr):\n"
            "    if not arr: return []\n"
            "    return qs([x for x in arr[1:] if x < arr[0]]) + [arr[0]] + qs([x for x in arr[1:] if x >= arr[0]])\n"
            "```\n"
            "Let me know if you have questions!"
        )
        state = make_state(
            [
                HumanMessage(content="什么是快速排序算法？请解释一下原理"),
                AIMessage(content=snippet_msg),
            ]
        )
        runtime = Runtime(context={"workspace_path": str(tmp_path)})

        mock_loop_guard = MagicMock()
        mock_loop_guard._window = []

        with patch(LOOP_GUARD_PATCH, return_value=mock_loop_guard):
            res = await self.guard.aafter_model(state, runtime)

        # No critical error blocking for short educational explanation
        assert res is None
