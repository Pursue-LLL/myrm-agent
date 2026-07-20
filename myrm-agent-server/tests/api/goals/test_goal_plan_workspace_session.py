"""Goal plan API reads todos from the chat-prefixed workspace session."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from myrm_agent_harness.agent.meta_tools.progress.schemas import TodoItem, TodoStatus, TodoStore
from myrm_agent_harness.agent.meta_tools.progress.storage import write_todos_sync_to_workspace
from myrm_agent_harness.toolkits.code_execution import create_workspace_service


@pytest.fixture
def goals_client(tmp_path: Path):
    from app.api.goals.router import router as goals_router

    app = FastAPI()
    app.include_router(goals_router, prefix="/api/v1")

    feature_set = MagicMock()
    feature_set.enabled.return_value = True

    with patch("app.api.goals.router.get_features", return_value=feature_set):
        with TestClient(app) as test_client:
            yield test_client, tmp_path


@pytest.mark.asyncio
async def test_get_goal_plan_uses_chat_workspace_session(goals_client: tuple[TestClient, Path]) -> None:
    test_client, tmp_path = goals_client
    chat_id = "session-uuid-1"

    workspace_svc = create_workspace_service(root_dir=tmp_path)
    workspace = await workspace_svc.get_or_create(session_id=f"chat_{chat_id}")
    workspace_root = workspace_svc.get_workspace_absolute_path(workspace)

    write_todos_sync_to_workspace(
        workspace_root,
        TodoStore(
            goal="Prepare launch checklist",
            todos=[TodoItem(id="todo_1", content="Draft outline", status=TodoStatus.PENDING)],
        ),
    )

    with patch("app.config.settings.get_settings") as mock_settings:
        mock_settings.return_value.database.harness_dir = str(tmp_path)
        response = test_client.get(f"/api/v1/goals/{chat_id}/plan")

    assert response.status_code == 200
    payload = response.json()
    assert payload["plan"] is not None
    assert payload["plan"]["goal"] == "Prepare launch checklist"
    assert payload["plan"]["steps"][0]["step_id"] == "todo_1"
    assert payload["plan"]["steps"][0]["description"] == "Draft outline"


@pytest.mark.asyncio
async def test_get_goal_dag_reads_workspace_todos(goals_client: tuple[TestClient, Path]) -> None:
    test_client, tmp_path = goals_client
    chat_id = "session-dag-1"

    workspace_svc = create_workspace_service(root_dir=tmp_path)
    workspace = await workspace_svc.get_or_create(session_id=f"chat_{chat_id}")
    workspace_root = workspace_svc.get_workspace_absolute_path(workspace)

    write_todos_sync_to_workspace(
        workspace_root,
        TodoStore(
            goal="DAG compat",
            todos=[
                TodoItem(id="todo_a", content="Step A", status=TodoStatus.PENDING),
                TodoItem(id="todo_b", content="Step B", status=TodoStatus.COMPLETED),
            ],
        ),
    )

    with patch("app.config.settings.get_settings") as mock_settings:
        mock_settings.return_value.database.harness_dir = str(tmp_path)
        response = test_client.get(f"/api/v1/goals/{chat_id}/dag")

    assert response.status_code == 200
    payload = response.json()
    assert payload["edges"] == []
    assert len(payload["nodes"]) == 2
    assert payload["nodes"][0]["id"] == "todo_a"
    assert payload["nodes"][0]["data"]["label"] == "Step A"
    assert payload["nodes"][1]["data"]["status"] == "completed"
