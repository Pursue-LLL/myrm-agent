"""E2E Test for Dynamic Workflow Engine

This test verifies that sending a request with `use_workflow=True`
correctly routes to the Dynamic Workflow Engine, bypassing the standard
agent pipeline, and yields the expected workflow status events.
"""

import json

import pytest
from fastapi.testclient import TestClient

from tests.api.agent.utils import check_e2e_errors, get_model_selection


def test_dynamic_workflow_e2e(client: TestClient):
    """Test that use_workflow=True triggers the dynamic workflow engine."""
    query = "Please analyze the codebase and write a summary."

    payload = {
        "query": query,
        "use_workflow": True,
        "chat_id": "test_chat_123",
        "message_id": "test_msg_456",
        "user_instructions": "Be concise.",
        "model_selection": get_model_selection(),
    }

    with client.stream("POST", "/api/v1/agents/agent-stream", json=payload) as response:
        if response.status_code != 200:
            response.read()
            pytest.fail(f"HTTP {response.status_code}: {response.text}")
        assert response.status_code == 200

        collected_data = []
        for line in response.iter_lines():
            if not line or not line.startswith("data: "):
                continue
            try:
                data = json.loads(line[6:])
                if isinstance(data, dict):
                    collected_data.append(data)
            except json.JSONDecodeError:
                pass

    assert len(collected_data) > 0, "Should have events"

    check_e2e_errors(collected_data)

    status_events = [d for d in collected_data if d.get("type") == "status"]
    step_keys = [d.get("step_key") for d in status_events if d.get("step_key")]

    assert "workflow_init" in step_keys, "Missing workflow_init step"
    assert "workflow_planning" in step_keys, "Missing workflow_planning step"
    assert "workflow_execution" in step_keys, "Missing workflow_execution step"

    content_events = [d for d in collected_data if d.get("type") == "content"]
    message_events = [d for d in collected_data if d.get("type") == "message"]
    assert content_events or message_events, "Missing final output event"

    final_content = "".join(str(d.get("content", "") or d.get("data", "")) for d in content_events + message_events)
    assert len(final_content) > 0, "Workflow should produce non-empty summarized output"


def _collect_workflow_events(client: TestClient, payload: dict[str, object]) -> list[dict[str, object]]:
    with client.stream("POST", "/api/v1/agents/agent-stream", json=payload) as response:
        if response.status_code != 200:
            response.read()
            pytest.fail(f"HTTP {response.status_code}: {response.text}")
        collected: list[dict[str, object]] = []
        for line in response.iter_lines():
            if not line or not line.startswith("data: "):
                continue
            try:
                data = json.loads(line[6:])
                if isinstance(data, dict):
                    collected.append(data)
            except json.JSONDecodeError:
                pass
    return collected


def test_dynamic_workflow_deterministic_id(client: TestClient):
    """workflow_id must be derived deterministically from chat_id + message_id."""
    import hashlib
    import uuid

    chat_id = f"det_chat_{uuid.uuid4().hex[:8]}"
    message_id = f"det_msg_{uuid.uuid4().hex[:8]}"
    base_payload = {
        "query": "Compute 2+2 with a simple script.",
        "use_workflow": True,
        "chat_id": chat_id,
        "message_id": message_id,
        "model_selection": get_model_selection(),
    }
    hash_input = f"{chat_id}:{message_id}".encode("utf-8")
    expected_wf = f"wf_{hashlib.md5(hash_input).hexdigest()[:12]}"

    events = _collect_workflow_events(client, base_payload)
    check_e2e_errors(events)

    wf_id: str | None = None
    for event in events:
        if event.get("type") == "status" and event.get("step_key") == "workflow_init" and event.get("status") == "success":
            data = event.get("data", {})
            if isinstance(data, dict):
                wf_id = data.get("workflow_id")
                break

    assert wf_id is not None, "No workflow_id found in workflow_init status event"
    assert wf_id == expected_wf


def test_use_workflow_false_uses_standard_pipeline(client: TestClient):
    """use_workflow=False must NOT emit workflow_init status events."""
    payload = {
        "query": "Reply with exactly: PLAIN_OK",
        "use_workflow": False,
        "chat_id": "plain_chat_001",
        "message_id": "plain_msg_001",
        "action_mode": "agent",
        "model_selection": get_model_selection(),
    }
    collected = _collect_workflow_events(client, payload)
    check_e2e_errors(collected)
    step_keys = [d.get("step_key") for d in collected if d.get("type") == "status" and d.get("step_key")]
    assert "workflow_init" not in step_keys
