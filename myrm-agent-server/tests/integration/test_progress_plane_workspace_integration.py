"""Integration: server profile flags + harness workspace SSOT for progress planes.

No LLM — verifies the business→harness wiring and guard read path.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.services.agent.profile_resolver import (
    DEFAULT_ENABLED_BUILTIN_TOOLS,
    resolve_builtin_tool_flags,
)
from myrm_agent_harness.agent.execution_checklist.state import (
    ChecklistItem,
    ExecutionChecklistState,
    read_checklist_sync,
    save_checklist_to_workspace,
)
from myrm_agent_harness.agent.middlewares.completion_guard import _build_checklist
from myrm_agent_harness.agent.security.guards.loop_guard_types import CallRecord, SuccessLevel
from myrm_agent_harness.agent.sub_agents.planner.schemas import Plan, PlanStep
from myrm_agent_harness.agent.sub_agents.planner.storage import (
    PlannerStorage,
    read_plan_sync_from_workspace,
    workspace_plan_exists,
)


def test_profile_resolver_planning_and_task_tracking_flags() -> None:
    planning_flags = resolve_builtin_tool_flags(["planning"])
    assert planning_flags["enable_planning"] is True
    assert planning_flags["enable_task_tracking"] is False

    tracking_flags = resolve_builtin_tool_flags(["task_tracking"])
    assert tracking_flags["enable_task_tracking"] is True
    assert tracking_flags["enable_planning"] is False


def test_default_builtin_tools_exclude_progress_planes() -> None:
    flags = resolve_builtin_tool_flags(DEFAULT_ENABLED_BUILTIN_TOOLS)
    assert flags["enable_planning"] is False
    assert flags["enable_task_tracking"] is False


@pytest.mark.asyncio
async def test_workspace_plan_exists_uses_sandbox_not_global_storage(tmp_path: Path) -> None:
    workspace = tmp_path / "sandbox"
    plan_dir = workspace / "planner"
    plan_dir.mkdir(parents=True)
    plan_dir.joinpath("plan.json").write_text('{"goal":"g","reasoning":"r","steps":[]}', encoding="utf-8")
    backend = MagicMock()
    backend.exists = MagicMock(return_value=False)
    assert await workspace_plan_exists(backend, workspace_root=str(workspace), storage_prefix="/planner") is True
    backend.exists.assert_not_called()


@pytest.mark.asyncio
async def test_planner_workspace_write_matches_guard_read_path(tmp_path: Path) -> None:
    workspace = tmp_path / "sandboxes" / "chat_integration"
    workspace.mkdir(parents=True)
    backend = MagicMock()

    storage = PlannerStorage(backend, workspace_root=str(workspace))
    plan = Plan(
        goal="Integration goal",
        reasoning="Verify SSOT",
        steps=[
            PlanStep(
                step_id="1",
                description="Finish integration test",
                expected_output="Done",
                status="pending",
            )
        ],
    )
    await storage.save_plan(plan)

    plan_path = workspace / "planner" / "plan.json"
    assert plan_path.is_file()
    backend.write_text.assert_not_called()

    loaded = read_plan_sync_from_workspace(str(workspace), storage_prefix="/planner")
    assert loaded is not None
    assert loaded.goal == "Integration goal"

    records = [
        CallRecord(
            tool_name="file_write_tool",
            args_hash="w1",
            args={"path": "/out/report.md", "content": "x"},
            success_level=SuccessLevel.FULL_SUCCESS,
        ),
    ]
    checklist, has_critical = _build_checklist(records, workspace_root=str(workspace))
    assert has_critical
    assert "uncompleted steps in your Goal Plan" in checklist


@pytest.mark.asyncio
async def test_checklist_workspace_write_matches_guard_read_path(tmp_path: Path) -> None:
    workspace = tmp_path / "sandboxes" / "chat_checklist"
    workspace.mkdir(parents=True)

    state = ExecutionChecklistState(
        items=[ChecklistItem(id="1", content="Ship feature", status="pending")],
    )
    await save_checklist_to_workspace(str(workspace), state)

    assert read_checklist_sync(str(workspace)) is not None

    records = [
        CallRecord(
            tool_name="file_write_tool",
            args_hash="w1",
            args={"path": "/out/feature.md", "content": "x"},
            success_level=SuccessLevel.FULL_SUCCESS,
        ),
    ]
    checklist, has_critical = _build_checklist(records, workspace_root=str(workspace))
    assert has_critical
    assert "Execution checklist has incomplete items" in checklist


@pytest.mark.asyncio
async def test_guard_no_critical_when_plan_steps_completed(tmp_path: Path) -> None:
    workspace = tmp_path / "done_plan"
    workspace.mkdir()
    backend = MagicMock()
    storage = PlannerStorage(backend, workspace_root=str(workspace))
    plan = Plan(
        goal="Done",
        reasoning="All finished",
        steps=[
            PlanStep(
                step_id="1",
                description="Step",
                expected_output="OK",
                status="completed",
            )
        ],
    )
    await storage.save_plan(plan)
    records = [
        CallRecord(
            tool_name="file_write_tool",
            args_hash="w1",
            args={"path": "/out/x.md", "content": "x"},
            success_level=SuccessLevel.FULL_SUCCESS,
        ),
    ]
    checklist, has_critical = _build_checklist(records, workspace_root=str(workspace))
    assert not has_critical
    assert "uncompleted steps in your Goal Plan" not in checklist
