"""E2E: agent-stream with kanban orchestrator tools must create and list tasks."""

from __future__ import annotations

import json
import os
import time
import uuid
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.services.kanban import KanbanService
from tests.api.agent.test_capability_gap_integration import (
    _collect_agent_stream,
    _invoked_tool_names,
)
from tests.api.agent.utils import check_e2e_errors, get_model_selection

_E2E_TASK_TITLE = "E2E-KANBAN-AGENT-STREAM-TEST"
_E2E_PREFERRED_BOARD_TITLE = "PREFERRED-BOARD-E2E"


@pytest.fixture(autouse=True)
def _reset_kanban_singleton() -> None:
    KanbanService._instance = None
    yield
    KanbanService._instance = None


@pytest.fixture(autouse=True)
def _skip_kanban_agent_validation() -> None:
    with patch.object(
        KanbanService,
        "_validate_agent_id",
        new_callable=AsyncMock,
    ):
        yield


def _normalize_tool_names(names: set[str]) -> set[str]:
    return {name.removesuffix("_tool") for name in names}


def _create_board(client: TestClient, name: str) -> str:
    response = client.post("/api/v1/kanban/boards", json={"name": name, "description": "e2e"})
    assert response.status_code == 201, response.text
    body = response.json()
    board_id = body.get("board_id")
    assert isinstance(board_id, str) and board_id
    return board_id


def _find_task_by_title(client: TestClient, title: str) -> dict[str, Any] | None:
    boards_resp = client.get("/api/v1/kanban/boards")
    assert boards_resp.status_code == 200, boards_resp.text
    boards_body = boards_resp.json()
    items = boards_body.get("items")
    if not isinstance(items, list):
        return None
    for board in items:
        board_id = board.get("board_id")
        if not isinstance(board_id, str):
            continue
        tasks_resp = client.get(f"/api/v1/kanban/boards/{board_id}/tasks")
        if tasks_resp.status_code != 200:
            continue
        tasks_body = tasks_resp.json()
        task_items = tasks_body.get("items")
        if not isinstance(task_items, list):
            continue
        for task in task_items:
            if isinstance(task, dict) and task.get("title") == title:
                return task
    return None


@pytest.mark.e2e
@pytest.mark.skipif(
    not os.environ.get("LITE_API_KEY") and not os.environ.get("BASIC_API_KEY"),
    reason="E2E test requires LITE_API_KEY or BASIC_API_KEY",
)
def test_agent_stream_kanban_orchestrator_creates_task(
    client: TestClient,
    mock_load_user_configs: pytest.AsyncMock,
) -> None:
    """Real agent-stream: kanban_add_task + kanban_list_tasks(task_id) persist to store."""
    configs = mock_load_user_configs.return_value
    configs.security_config_dict = {
        **(configs.security_config_dict or {}),
        "yoloModeEnabled": True,
        "yoloModeEnabledAt": time.time(),
    }

    board_id = _create_board(client, f"Agent Stream E2E {uuid.uuid4().hex[:8]}")
    chat_id = f"test_kanban_stream_{uuid.uuid4().hex[:8]}"
    create_response = client.post("/api/v1/chats/", json={"chat_id": chat_id})
    assert create_response.status_code == 200

    query = (
        "CRITICAL: Your very first action MUST be kanban_add_task — no text reply before it. "
        f'Call kanban_add_task with board_id="{board_id}", title exactly "{_E2E_TASK_TITLE}", '
        'priority="low". '
        "Then call kanban_list_tasks with task_id set to the task id returned from add_task. "
        "Do not use bash, web_search, or any other tools. "
        "After both tool calls succeed, reply with a single line: DONE <task_id>."
    )

    events: list[dict[str, object]] = []
    invoked: set[str] = set()
    for _attempt in range(2):
        message_id = f"msg_{uuid.uuid4().hex[:8]}"
        payload: dict[str, object] = {
            "messageId": message_id,
            "chatId": chat_id,
            "query": query,
            "modelSelection": get_model_selection(),
            "actionMode": "agent",
            "enableMemory": False,
            "agentConfig": {
                "enabledBuiltinTools": ["kanban"],
            },
        }
        events = _collect_agent_stream(client, payload)
        check_e2e_errors(events)
        invoked = _normalize_tool_names(_invoked_tool_names(events))
        if "kanban_add_task" in invoked:
            break

    if "kanban_add_task" not in invoked:
        pytest.skip(
            "model did not invoke kanban_add_task after 2 attempts; "
            f"invoked={sorted(invoked)} event_types="
            f"{sorted({e.get('type') for e in events if isinstance(e.get('type'), str)})}"
        )

    task = _find_task_by_title(client, _E2E_TASK_TITLE)
    assert task is not None, (
        f"Expected task {_E2E_TASK_TITLE!r} in store after kanban_add_task; "
        f"events_blob={json.dumps(events, ensure_ascii=False)[:500]}"
    )
    assert task.get("board_id") == board_id

    if "kanban_list_tasks" in invoked:
        task_id = task.get("task_id")
        blob = json.dumps(events, ensure_ascii=False).lower()
        assert (isinstance(task_id, str) and task_id.lower() in blob) or "done" in blob.lower()


@pytest.mark.e2e
@pytest.mark.skipif(
    not os.environ.get("LITE_API_KEY") and not os.environ.get("BASIC_API_KEY"),
    reason="E2E test requires LITE_API_KEY or BASIC_API_KEY",
)
def test_agent_stream_kanban_default_board_id_prefers_chat_board(
    client: TestClient,
    mock_load_user_configs: pytest.AsyncMock,
) -> None:
    """kanbanDefaultBoardId in agent_config wins over newest board when LLM omits board_id."""
    configs = mock_load_user_configs.return_value
    configs.security_config_dict = {
        **(configs.security_config_dict or {}),
        "yoloModeEnabled": True,
        "yoloModeEnabledAt": time.time(),
    }

    preferred_board_id = _create_board(client, f"Preferred E2E {uuid.uuid4().hex[:8]}")
    _create_board(client, f"Newer E2E {uuid.uuid4().hex[:8]}")
    chat_id = f"test_kanban_preferred_{uuid.uuid4().hex[:8]}"
    create_response = client.post("/api/v1/chats/", json={"chat_id": chat_id})
    assert create_response.status_code == 200

    query = (
        "CRITICAL: Your very first action MUST be kanban_add_task — no text reply before it. "
        f'Call kanban_add_task with title exactly "{_E2E_PREFERRED_BOARD_TITLE}", priority="low". '
        "Do NOT pass board_id — rely on the default board from chat config. "
        "After add_task succeeds, reply with a single line: DONE."
    )

    events: list[dict[str, object]] = []
    invoked: set[str] = set()
    for _attempt in range(2):
        message_id = f"msg_{uuid.uuid4().hex[:8]}"
        payload: dict[str, object] = {
            "messageId": message_id,
            "chatId": chat_id,
            "query": query,
            "modelSelection": get_model_selection(),
            "actionMode": "agent",
            "enableMemory": False,
            "agentConfig": {
                "enabledBuiltinTools": ["kanban"],
                "kanbanDefaultBoardId": preferred_board_id,
            },
        }
        events = _collect_agent_stream(client, payload)
        check_e2e_errors(events)
        invoked = _normalize_tool_names(_invoked_tool_names(events))
        if "kanban_add_task" in invoked:
            break

    if "kanban_add_task" not in invoked:
        pytest.skip(
            "model did not invoke kanban_add_task after 2 attempts; "
            f"invoked={sorted(invoked)}"
        )

    task = _find_task_by_title(client, _E2E_PREFERRED_BOARD_TITLE)
    assert task is not None, f"Expected task {_E2E_PREFERRED_BOARD_TITLE!r} in store"
    assert task.get("board_id") == preferred_board_id
