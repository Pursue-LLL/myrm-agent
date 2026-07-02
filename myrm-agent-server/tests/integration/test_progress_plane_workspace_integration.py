"""Progress plane workspace integration — todo SSOT + CompletionGuard."""

from __future__ import annotations

from pathlib import Path

import pytest

from myrm_agent_harness.agent.middlewares.completion_guard import _build_checklist
from myrm_agent_harness.agent.security.guards.loop_guard_types import CallRecord, SuccessLevel
from myrm_agent_harness.agent.meta_tools.progress.schemas import TodoItem, TodoStatus, TodoStore
from myrm_agent_harness.agent.meta_tools.progress.storage import (
    read_todos_sync_from_workspace,
    workspace_todos_exist,
    write_todos_sync_to_workspace,
)
from myrm_agent_harness.core.security.tool_registry import TOOL_GROUP_MAP
from app.services.agent.profile_resolver import resolve_builtin_tool_flags


class _ExistsBackend:
    async def exists(self, path: str) -> bool:
        return Path(path).is_file()


@pytest.mark.asyncio
async def test_profile_resolver_planning_flag() -> None:
    planning_flags = resolve_builtin_tool_flags(["planning"])
    assert planning_flags["enable_planning"] is True

    flags = resolve_builtin_tool_flags(["web_search", "memory"])
    assert flags["enable_planning"] is False


def test_planning_group_maps_to_todo_write() -> None:
    assert TOOL_GROUP_MAP["planning"] == frozenset({"todo_write"})


@pytest.mark.asyncio
async def test_workspace_todos_exist(tmp_path: Path) -> None:
    workspace = tmp_path / "chat"
    progress_dir = workspace / ".myrm" / "progress"
    progress_dir.mkdir(parents=True)
    progress_dir.joinpath("todos.json").write_text('{"todos":[]}', encoding="utf-8")

    backend = _ExistsBackend()
    assert await workspace_todos_exist(backend, workspace_root=str(workspace)) is True


def test_todos_write_matches_guard_read_path(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    store = TodoStore(
        goal="OAuth migration",
        todos=[TodoItem(id="1", content="Update config", status=TodoStatus.PENDING)],
    )
    write_todos_sync_to_workspace(str(workspace), store)

    loaded = read_todos_sync_from_workspace(str(workspace))
    assert loaded is not None
    assert len(loaded.todos) == 1

    records = [
        CallRecord(
            tool_name="file_write_tool",
            args_hash="w1",
            args={"path": "/src/app.py", "content": "x"},
            success_level=SuccessLevel.FULL_SUCCESS,
        )
    ]
    checklist, has_critical = _build_checklist(records, workspace_root=str(workspace))
    assert has_critical
    assert "incomplete todos" in checklist


def test_completed_todos_do_not_block_guard(tmp_path: Path) -> None:
    workspace = tmp_path / "ws_done"
    workspace.mkdir()
    store = TodoStore(
        goal="Done",
        todos=[TodoItem(id="1", content="Finish", status=TodoStatus.COMPLETED)],
    )
    write_todos_sync_to_workspace(str(workspace), store)

    checklist, has_critical = _build_checklist([], workspace_root=str(workspace))
    assert not has_critical
    assert "incomplete todos" not in checklist
