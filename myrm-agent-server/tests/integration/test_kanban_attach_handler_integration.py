"""Integration: kanban attach handler + orchestrator unblock on real SQLite store."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from myrm_agent_harness.toolkits.kanban.types import TaskStatus

from app.services.kanban import KanbanService
from app.services.kanban.kanban_attach_handler import create_kanban_attach_handler
from app.services.kanban.task_attachment_ids import load_task_attachment_ids


@pytest.fixture(autouse=True)
def _reset_kanban_singleton() -> None:
    KanbanService._instance = None
    yield
    KanbanService._instance = None


@pytest.fixture(autouse=True)
def _skip_agent_validation() -> None:  # type: ignore[misc]
    with patch.object(
        KanbanService,
        "_validate_agent_id",
        new_callable=AsyncMock,
    ):
        yield


@pytest.mark.integration
@pytest.mark.asyncio
async def test_attach_handler_persists_path_attachment_on_sqlite(tmp_path: Path) -> None:
    """Worker attach callback → files service + attachment_ids_json on real DB."""
    svc = KanbanService.get_instance()
    board = await svc.create_board("Attach Handler Integ")
    workspace = tmp_path / "ws"
    workspace.mkdir()
    sample = workspace / "deliverable.txt"
    sample.write_text("integration payload", encoding="utf-8")

    task = await svc.add_task(board.board_id, "Attach via handler")
    task.workspace_path = str(workspace)
    await svc.store.save_task(task)

    handler = create_kanban_attach_handler(svc.store)
    result = await handler(task.task_id, "path", "deliverable.txt")

    persisted = await load_task_attachment_ids(task.task_id)
    assert len(persisted) == 1
    assert result["file_id"] == persisted[0]
    assert result["attachment_count"] == 1
    assert result["filename"] == "deliverable.txt"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_orchestrator_unblock_tool_on_blocked_sqlite_task() -> None:
    """kanban_unblock tool invoke transitions blocked → ready on real store."""
    from app.ai_agents.general_agent.factory import _setup_kanban_tools

    svc = KanbanService.get_instance()
    board = await svc.create_board("Unblock Integ Board")
    created = await svc.add_task(board.board_id, "Blocked for unblock")
    blocked = await svc.get_task(created.task_id)
    assert blocked is not None
    blocked.status = TaskStatus.BLOCKED
    blocked.blocked_reason = "integration hold"
    await svc.store.save_task(blocked)

    agent_wrapper = SimpleNamespace(
        kanban_tool_mode="orchestrator",
        kanban_current_task_id=None,
        agent_id="agent-integ-unblock",
    )
    tools: list[object] = []
    await _setup_kanban_tools(agent_wrapper, tools)

    unblock_tool = next(t for t in tools if getattr(t, "name", None) == "kanban_unblock")
    raw = await unblock_tool.ainvoke({"task_id": created.task_id, "reason": "approved"})
    data = json.loads(raw)

    assert data["status"] == "unblocked"
    refreshed = await svc.get_task(created.task_id)
    assert refreshed is not None
    assert refreshed.status == TaskStatus.READY
