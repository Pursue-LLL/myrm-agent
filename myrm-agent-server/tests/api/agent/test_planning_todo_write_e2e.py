"""E2E: planning builtin tool binds todo_write and persists workspace todos."""

from __future__ import annotations

import json
import os
import uuid

import pytest
from fastapi.testclient import TestClient

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

    plan_response = client.get(f"/api/v1/goals/{chat_id}/plan")
    assert plan_response.status_code == 200
    plan_payload = plan_response.json().get("plan")
    assert plan_payload is not None, "Goal plan API should hydrate todos from workspace SSOT"
    assert plan_payload.get("goal") == "Integration test"
    step_ids = {step.get("step_id") for step in plan_payload.get("steps", [])}
    assert {"step_a", "step_b"}.issubset(step_ids)
