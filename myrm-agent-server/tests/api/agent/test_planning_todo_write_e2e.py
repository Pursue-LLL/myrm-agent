"""E2E: planning builtin tool binds todo_write and persists workspace todos."""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from myrm_agent_harness.agent.meta_tools.progress.storage import read_todos_sync_from_workspace
from myrm_agent_harness.toolkits.code_execution import create_workspace_service

from app.config.settings import get_settings
from app.platform_utils.workspace_session import to_workspace_session_id
from tests.api.agent.utils import check_e2e_errors, get_lite_model_selection


def _collect_agent_stream(client: TestClient, payload: dict[str, object]) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    with client.stream("POST", "/api/v1/agents/agent-stream", json=payload, timeout=180.0) as response:
        assert response.status_code == 200
        for line in response.iter_lines():
            if not line or not line.startswith("data: "):
                continue
            raw = line[6:]
            if raw == "[DONE]":
                break
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict):
                events.append(data)
    return events


async def _read_workspace_todos(chat_id: str) -> object | None:
    harness_root = Path(get_settings().database.harness_dir)
    workspace_svc = create_workspace_service(root_dir=harness_root)
    workspace = await workspace_svc.get_or_create(session_id=to_workspace_session_id(chat_id))
    workspace_root = workspace_svc.get_workspace_absolute_path(workspace)
    return read_todos_sync_from_workspace(workspace_root)


@pytest.mark.e2e
@pytest.mark.skipif(
    not os.environ.get("LITE_API_KEY") and not os.environ.get("BASIC_API_KEY"),
    reason="E2E test requires LITE_API_KEY or BASIC_API_KEY",
)
def test_planning_todo_write_persists_and_emits_tasks_steps(client: TestClient) -> None:
    chat_id = f"planning_e2e_{uuid.uuid4().hex[:10]}"
    create_response = client.post("/api/v1/chats/", json={"chat_id": chat_id})
    assert create_response.status_code == 200

    payload: dict[str, object] = {
        "messageId": f"msg_{uuid.uuid4().hex[:8]}",
        "chatId": chat_id,
        "query": (
            "You MUST call the todo_write tool exactly once with merge=false and goal "
            "'Integration test'. Todos: "
            '[{"id":"step_a","content":"Alpha","status":"pending"},'
            '{"id":"step_b","content":"Beta","status":"pending"}]. '
            "Do not use any other tools. After todo_write succeeds, reply DONE."
        ),
        "modelSelection": get_lite_model_selection(),
        "actionMode": "agent",
        "agentConfig": {
            "enabledBuiltinTools": ["planning"],
        },
    }

    events = _collect_agent_stream(client, payload)
    check_e2e_errors(events)

    todo_step_events = [
        event
        for event in events
        if event.get("type") == "tasks_steps" and event.get("tool_name") == "todo_write"
    ]
    assert todo_step_events, "Expected tasks_steps events for todo_write"

    store = asyncio.run(_read_workspace_todos(chat_id))
    assert store is not None, "todo_write should persist todos.json in workspace SSOT"
    assert store.goal == "Integration test"
    step_ids = {item.id for item in store.todos}
    assert {"step_a", "step_b"}.issubset(step_ids)


@pytest.mark.e2e
@pytest.mark.skipif(
    not os.environ.get("LITE_API_KEY") and not os.environ.get("BASIC_API_KEY"),
    reason="E2E test requires LITE_API_KEY or BASIC_API_KEY",
)
def test_planning_resume_loads_todo_write_without_planning_flag(client: TestClient) -> None:
    """Second turn: planning off in config but workspace todos exist → todo_write still available."""
    chat_id = f"planning_resume_{uuid.uuid4().hex[:10]}"
    assert client.post("/api/v1/chats/", json={"chat_id": chat_id}).status_code == 200

    seed_payload: dict[str, object] = {
        "messageId": f"msg_{uuid.uuid4().hex[:8]}",
        "chatId": chat_id,
        "query": (
            "Call todo_write exactly once (merge=false, goal='Resume test'): "
            '[{"id":"r1","content":"Resume step","status":"pending"}]. '
            "No other tools. Reply SEEDED."
        ),
        "modelSelection": get_lite_model_selection(),
        "actionMode": "agent",
        "agentConfig": {"enabledBuiltinTools": ["planning"]},
    }
    seed_events = _collect_agent_stream(client, seed_payload)
    check_e2e_errors(seed_events)
    assert asyncio.run(_read_workspace_todos(chat_id)) is not None

    resume_payload: dict[str, object] = {
        "messageId": f"msg_{uuid.uuid4().hex[:8]}",
        "chatId": chat_id,
        "query": (
            "Call todo_write once with merge=true to mark r1 completed. "
            "No other tools. Reply RESUMED."
        ),
        "modelSelection": get_lite_model_selection(),
        "actionMode": "agent",
        "agentConfig": {"enabledBuiltinTools": ["web_search", "memory"]},
    }
    resume_events = _collect_agent_stream(client, resume_payload)
    check_e2e_errors(resume_events)

    store = asyncio.run(_read_workspace_todos(chat_id))
    assert store is not None
    resume_item = next((item for item in store.todos if item.id == "r1"), None)
    assert resume_item is not None
    assert resume_item.status.value == "completed"


@pytest.mark.e2e
@pytest.mark.skipif(
    not os.environ.get("LITE_API_KEY") and not os.environ.get("BASIC_API_KEY"),
    reason="E2E test requires LITE_API_KEY or BASIC_API_KEY",
)
def test_planning_default_off_no_todo_write_without_planning(client: TestClient) -> None:
    """Default tools (no planning) must not persist todos when model is told not to use bash/file."""
    chat_id = f"planning_off_{uuid.uuid4().hex[:10]}"
    assert client.post("/api/v1/chats/", json={"chat_id": chat_id}).status_code == 200

    payload: dict[str, object] = {
        "messageId": f"msg_{uuid.uuid4().hex[:8]}",
        "chatId": chat_id,
        "query": "Reply with exactly the word PLAIN only. Do not use any tools.",
        "modelSelection": get_lite_model_selection(),
        "actionMode": "agent",
        "agentConfig": {"enabledBuiltinTools": ["web_search", "memory"]},
    }
    events = _collect_agent_stream(client, payload)
    check_e2e_errors(events)

    todo_events = [e for e in events if e.get("tool_name") == "todo_write"]
    assert not todo_events, "todo_write must not appear when planning is disabled and no prior todos"
    assert asyncio.run(_read_workspace_todos(chat_id)) is None
