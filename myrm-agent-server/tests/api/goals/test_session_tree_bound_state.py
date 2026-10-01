"""Tests for session-tree bound branch state replayer and rewind synchronization.

[INPUT]
- app.api.goals.router::router (POS: Goal endpoints router)
- app.api.goals.plan::resolve_session_todo_store, sync_workspace_todos_after_rewind (POS: Target functions)
- myrm_agent_harness.agent.meta_tools.progress.schemas::TodoItem, TodoStatus, TodoStore
- myrm_agent_harness.runtime.context.tree_state::create_compaction_todo_anchor

[OUTPUT]
- Test cases verifying branch isolation, workspace fallback, and atomic rewind alignment.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from myrm_agent_harness.agent.meta_tools.progress.schemas import (
    TodoItem,
    TodoStatus,
    TodoStore,
)
from myrm_agent_harness.agent.meta_tools.progress.storage import (
    read_todos_sync_from_workspace,
    todos_path,
    write_todos_sync_to_workspace,
)
from myrm_agent_harness.runtime.context.tree_state import create_compaction_todo_anchor
from myrm_agent_harness.toolkits.code_execution import create_workspace_service

from app.api.goals.router import router as goals_router
from app.database.dto import MessageDTO


@pytest.fixture
def test_client_fixture(tmp_path: Path):
    app = FastAPI()
    app.include_router(goals_router, prefix="/api/v1")

    feature_set = MagicMock()
    feature_set.enabled.return_value = True

    with patch("app.api.goals.router.get_features", return_value=feature_set):
        with TestClient(app) as client:
            yield client, tmp_path


def _create_fake_message(
    chat_id: str,
    content: str,
    extra_data: dict[str, object] | None = None,
) -> MessageDTO:
    now = datetime.now(UTC)
    return MessageDTO(
        id=f"msg-{now.timestamp()}",
        chat_id=chat_id,
        role="assistant",
        content=content,
        sent_at=now,
        sent_timezone="UTC",
        created_at=now,
        extra_data=extra_data,
        is_active=True,
    )


@pytest.mark.asyncio
async def test_get_goal_plan_prioritizes_active_branch_over_workspace(
    test_client_fixture: tuple[TestClient, Path],
) -> None:
    """Active conversation branch state takes absolute priority over physical workspace file."""
    client, tmp_path = test_client_fixture
    chat_id = "session-branch-priority-1"

    workspace_svc = create_workspace_service(root_dir=tmp_path)
    workspace = await workspace_svc.get_or_create(session_id=f"chat_{chat_id}")
    workspace_root = workspace_svc.get_workspace_absolute_path(workspace)

    # 1. Contaminate physical workspace with an outdated or conflicting store
    write_todos_sync_to_workspace(
        workspace_root,
        TodoStore(
            goal="Outdated workspace goal",
            todos=[TodoItem(id="old_1", content="Stale item", status=TodoStatus.COMPLETED)],
            revision=1,
        ),
    )

    # 2. Prepare active message branch with authoritative state
    branch_store = TodoStore(
        goal="Authoritative branch goal",
        todos=[
            TodoItem(id="step_1", content="Explore repository", status=TodoStatus.COMPLETED),
            TodoItem(id="step_2", content="Refactor architecture", status=TodoStatus.IN_PROGRESS),
        ],
        revision=2,
    )
    branch_message = _create_fake_message(
        chat_id=chat_id,
        content=json.dumps({"todos": [t.model_dump() for t in branch_store.todos], "summary": {}}),
        extra_data={"tool_result_details": {"todos": [t.model_dump() for t in branch_store.todos]}},
    )

    with patch("app.config.settings.get_settings") as mock_settings:
        mock_settings.return_value.database.harness_dir = str(tmp_path)
        with patch("app.services.chat.chat_service.ChatService.get_all_messages", new_callable=AsyncMock) as mock_msgs:
            mock_msgs.return_value = [branch_message]

            response = client.get(f"/api/v1/goals/{chat_id}/plan")

    assert response.status_code == 200
    plan = response.json().get("plan")
    assert plan is not None
    assert plan["goal"] == "Authoritative branch goal" or plan["steps"][0]["step_id"] == "step_1"
    assert len(plan["steps"]) == 2
    assert plan["steps"][0]["step_id"] == "step_1"
    assert plan["steps"][1]["step_id"] == "step_2"
    assert plan["steps"][1]["status"] == "in_progress"


@pytest.mark.asyncio
async def test_forked_branches_isolation(test_client_fixture: tuple[TestClient, Path]) -> None:
    """Parent and child forked sessions retain independent plan states."""
    client, tmp_path = test_client_fixture
    parent_chat_id = "parent-session-1"
    child_chat_id = "child-session-fork-2"

    parent_store = TodoStore(
        goal="Base plan",
        todos=[TodoItem(id="init", content="Initial setup", status=TodoStatus.COMPLETED)],
        revision=1,
    )
    child_store = TodoStore(
        goal="Branch specialized plan",
        todos=[
            TodoItem(id="init", content="Initial setup", status=TodoStatus.COMPLETED),
            TodoItem(id="child_task", content="Fork specific experiment", status=TodoStatus.IN_PROGRESS),
        ],
        revision=2,
    )

    parent_msg = _create_fake_message(
        chat_id=parent_chat_id,
        content="",
        extra_data={"tool_result_details": parent_store.model_dump()},
    )
    child_msg = _create_fake_message(
        chat_id=child_chat_id,
        content="",
        extra_data={"tool_result_details": child_store.model_dump()},
    )

    async def fake_get_all_messages(session_id: str) -> list[MessageDTO]:
        if session_id == parent_chat_id:
            return [parent_msg]
        if session_id == child_chat_id:
            return [child_msg]
        return []

    with patch("app.config.settings.get_settings") as mock_settings:
        mock_settings.return_value.database.harness_dir = str(tmp_path)
        with patch("app.services.chat.chat_service.ChatService.get_all_messages", side_effect=fake_get_all_messages):
            resp_parent = client.get(f"/api/v1/goals/{parent_chat_id}/plan")
            resp_child = client.get(f"/api/v1/goals/{child_chat_id}/plan")

    assert resp_parent.status_code == 200
    assert len(resp_parent.json()["plan"]["steps"]) == 1
    assert resp_parent.json()["plan"]["steps"][0]["step_id"] == "init"

    assert resp_child.status_code == 200
    assert len(resp_child.json()["plan"]["steps"]) == 2
    assert resp_child.json()["plan"]["steps"][1]["step_id"] == "child_task"


@pytest.mark.asyncio
async def test_compaction_anchor_replaying(test_client_fixture: tuple[TestClient, Path]) -> None:
    """State successfully re-establishes from compaction anchor followed by subsequent updates."""
    client, tmp_path = test_client_fixture
    chat_id = "session-compaction-1"

    base_store = TodoStore(
        goal="Compacted milestone",
        todos=[
            TodoItem(id="p1", content="Step 1", status=TodoStatus.COMPLETED),
            TodoItem(id="p2", content="Step 2", status=TodoStatus.COMPLETED),
        ],
        revision=10,
    )
    anchor_extra = create_compaction_todo_anchor(base_store)
    compaction_msg = _create_fake_message(
        chat_id=chat_id,
        content="Summary of earlier conversation turns",
        extra_data=anchor_extra,
    )

    next_store = TodoStore(
        goal="Compacted milestone",
        todos=[
            TodoItem(id="p1", content="Step 1", status=TodoStatus.COMPLETED),
            TodoItem(id="p2", content="Step 2", status=TodoStatus.COMPLETED),
            TodoItem(id="p3", content="Step 3 active", status=TodoStatus.IN_PROGRESS),
        ],
        revision=11,
    )
    followup_msg = _create_fake_message(
        chat_id=chat_id,
        content="",
        extra_data={"tool_result_details": next_store.model_dump()},
    )

    with patch("app.config.settings.get_settings") as mock_settings:
        mock_settings.return_value.database.harness_dir = str(tmp_path)
        with patch("app.services.chat.chat_service.ChatService.get_all_messages", new_callable=AsyncMock) as mock_msgs:
            mock_msgs.return_value = [compaction_msg, followup_msg]

            response = client.get(f"/api/v1/goals/{chat_id}/dag")

    assert response.status_code == 200
    nodes = response.json().get("nodes", [])
    assert len(nodes) == 3
    assert nodes[2]["id"] == "p3"
    assert nodes[2]["data"]["status"] == "in_progress"


@pytest.mark.asyncio
async def test_sync_workspace_todos_after_rewind_clears_stale_file(tmp_path: Path) -> None:
    """Rewinding to before any todos existed safely deletes leftover workspace progress file."""
    from app.api.goals.plan import sync_workspace_todos_after_rewind

    chat_id = "rewind-clean-session"
    workspace_svc = create_workspace_service(root_dir=tmp_path)
    workspace = await workspace_svc.get_or_create(session_id=f"chat_{chat_id}")
    workspace_root = workspace_svc.get_workspace_absolute_path(workspace)

    # Pre-populate workspace with leftover future tasks
    write_todos_sync_to_workspace(
        workspace_root,
        TodoStore(todos=[TodoItem(id="future_task", content="Deleted turn", status=TodoStatus.COMPLETED)]),
    )
    assert todos_path(workspace_root).is_file()

    with patch("app.config.settings.get_settings") as mock_settings:
        mock_settings.return_value.database.harness_dir = str(tmp_path)
        with patch("app.services.chat.chat_service.ChatService.get_all_messages", new_callable=AsyncMock) as mock_msgs:
            # Remaining messages contain no todos
            mock_msgs.return_value = []
            await sync_workspace_todos_after_rewind(chat_id)

    # Verify stale workspace file was purged
    assert not todos_path(workspace_root).is_file()


@pytest.mark.asyncio
async def test_sync_workspace_todos_after_rewind_restores_earlier_state(tmp_path: Path) -> None:
    """Rewinding restores the earlier step's state in physical workspace."""
    from app.api.goals.plan import sync_workspace_todos_after_rewind

    chat_id = "rewind-revert-session"
    workspace_svc = create_workspace_service(root_dir=tmp_path)
    workspace = await workspace_svc.get_or_create(session_id=f"chat_{chat_id}")
    workspace_root = workspace_svc.get_workspace_absolute_path(workspace)

    # Workspace had advanced to step 2 completed
    write_todos_sync_to_workspace(
        workspace_root,
        TodoStore(
            todos=[
                TodoItem(id="s1", content="Step 1", status=TodoStatus.COMPLETED),
                TodoItem(id="s2", content="Step 2", status=TodoStatus.COMPLETED),
            ],
            revision=5,
        ),
    )

    # But rewind left only message with step 1 in_progress
    earlier_store = TodoStore(
        todos=[TodoItem(id="s1", content="Step 1", status=TodoStatus.IN_PROGRESS)],
        revision=2,
    )
    remaining_msg = _create_fake_message(
        chat_id=chat_id,
        content="",
        extra_data={"tool_result_details": earlier_store.model_dump()},
    )

    with patch("app.config.settings.get_settings") as mock_settings:
        mock_settings.return_value.database.harness_dir = str(tmp_path)
        with patch("app.services.chat.chat_service.ChatService.get_all_messages", new_callable=AsyncMock) as mock_msgs:
            mock_msgs.return_value = [remaining_msg]
            await sync_workspace_todos_after_rewind(chat_id)

    # Workspace should now reflect the rewound earlier state
    synced = read_todos_sync_from_workspace(workspace_root)
    assert synced is not None
    assert len(synced.todos) == 1
    assert synced.todos[0].id == "s1"
    assert synced.todos[0].status == TodoStatus.IN_PROGRESS


def test_stream_collector_captures_and_persists_tool_result_details() -> None:
    """StreamContentCollector must capture tool_result_details from tasks_steps into extra_data."""
    from app.services.agent.streaming_support.stream_collector import StreamContentCollector

    collector = StreamContentCollector(chat_id="test_chat")

    details_payload = {
        "goal": "Build authentication",
        "revision": 2,
        "todos": [
            {"id": "t1", "content": "Create User model", "status": "completed"},
            {"id": "t2", "content": "JWT handler", "status": "in_progress"},
        ],
    }

    # Feed tasks_steps carrying tool_result_details
    collector.feed_event(
        {
            "type": "tasks_steps",
            "step_key": "progress_root",
            "tool_name": "todo_write",
            "tool_result_details": details_payload,
            "data": [{"text": "Build authentication"}],
        }
    )

    extra = collector.extra_data
    assert extra is not None
    assert "tool_result_details" in extra
    assert extra["tool_result_details"] == details_payload

    # Verify folded state from the collected extra_data
    from myrm_agent_harness.runtime.context.tree_state import fold_branch_todo_state

    msg = _create_fake_message(chat_id="test_chat", content="Plan updated", extra_data=extra)
    folded = fold_branch_todo_state([msg])
    assert folded is not None
    assert folded.goal == "Build authentication"
    assert len(folded.todos) == 2


@pytest.mark.asyncio
async def test_sync_workspace_todos_after_rewind_protects_existing_file(tmp_path: Path) -> None:
    """When messages exist but fold yields no store, workspace file is preserved rather than unlinked."""
    from app.services.chat.chat_todo_sync import sync_workspace_todos_after_rewind

    workspace_root = str(tmp_path / "ws_safe")
    chat_id = "chat_safe_rewind"

    # Pre-populate workspace with an existing file
    initial_store = TodoStore(
        todos=[TodoItem(id="x1", content="Existing step", status=TodoStatus.PENDING)],
        revision=1,
    )
    write_todos_sync_to_workspace(workspace_root, initial_store)
    assert todos_path(workspace_root).is_file()

    # Remaining messages exist (e.g. user prompt only, without tool details)
    msg_without_todos = _create_fake_message(
        chat_id=chat_id,
        content="Hello, help me write code",
        extra_data=None,
    )

    with patch("app.config.settings.get_settings") as mock_settings:
        mock_settings.return_value.database.harness_dir = str(tmp_path)
        with patch("app.services.chat.chat_service.ChatService.get_all_messages", new_callable=AsyncMock) as mock_msgs:
            mock_msgs.return_value = [msg_without_todos]
            with patch("app.services.chat.chat_todo_sync._resolve_workspace_root_safely", new_callable=AsyncMock) as mock_root:
                mock_root.return_value = workspace_root
                await sync_workspace_todos_after_rewind(chat_id)

    # Workspace file must NOT have been unlinked!
    assert todos_path(workspace_root).is_file()
    preserved = read_todos_sync_from_workspace(workspace_root)
    assert preserved is not None
    assert preserved.todos[0].id == "x1"

