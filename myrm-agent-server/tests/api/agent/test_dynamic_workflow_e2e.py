"""E2E Test for Dynamic Workflow Engine

Verifies use_workflow=True routes to the Dynamic Workflow Engine and that
plan_confirm HITL can be resolved via /plan-confirm-response before execution.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from tests.api.agent.utils import check_e2e_errors, get_model_selection


def _iter_sse_payloads(response: TestClient) -> Iterator[dict[str, object]]:
    for line in response.iter_lines():
        if not line or not line.startswith("data: "):
            continue
        try:
            data = json.loads(line[6:])
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            yield data


def _phase_payload(event: dict[str, object]) -> dict[str, object] | None:
    if event.get("type") != "status":
        return None
    raw = event.get("data")
    return raw if isinstance(raw, dict) else None


def _collect_workflow_events(
    client: TestClient,
    payload: dict[str, object],
    *,
    auto_confirm_message_id: str | None = None,
) -> list[dict[str, object]]:
    confirm_thread: threading.Thread | None = None

    if auto_confirm_message_id:

        def _auto_confirm_plan() -> None:
            from app.services.agent.streaming import PhaseWaiter

            plan_key = f"plan:{auto_confirm_message_id}"
            deadline = time.monotonic() + 120.0
            while time.monotonic() < deadline:
                if PhaseWaiter.get(plan_key) is not None:
                    client.post(
                        "/api/v1/agents/plan-confirm-response",
                        json={"messageId": auto_confirm_message_id, "action": "confirm"},
                    )
                    return
                time.sleep(0.25)

        confirm_thread = threading.Thread(target=_auto_confirm_plan, daemon=True)
        confirm_thread.start()

    with client.stream("POST", "/api/v1/agents/agent-stream", json=payload) as response:
        if response.status_code != 200:
            response.read()
            pytest.fail(f"HTTP {response.status_code}: {response.text}")
        collected = list(_iter_sse_payloads(response))

    if confirm_thread is not None:
        confirm_thread.join(timeout=5.0)

    return collected


def test_dynamic_workflow_e2e(client: TestClient):
    """use_workflow=True triggers DW, resolves plan_confirm, then executes."""
    message_id = "test_msg_456"
    payload = {
        "query": (
            "Orchestrate a workflow: spawn exactly one generalPurpose sub-agent "
            "to summarize the phrase HELLO_DW in one sentence, then print JSON results."
        ),
        "use_workflow": True,
        "chat_id": "test_chat_123",
        "message_id": message_id,
        "user_instructions": "Be concise.",
        "model_selection": get_model_selection(),
    }

    collected_data = _collect_workflow_events(
        client,
        payload,
        auto_confirm_message_id=message_id,
    )

    assert len(collected_data) > 0, "Should have events"
    check_e2e_errors(collected_data)

    phase_events = [
        phase
        for event in collected_data
        if (phase := _phase_payload(event)) is not None and phase.get("phase") == "plan_confirm"
    ]
    if phase_events:
        waiting = [p for p in phase_events if p.get("status") == "waiting"]
        assert waiting, "plan_confirm waiting event expected when script contains spawns"
        assert waiting[0].get("source") == "dynamic_workflow"

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


def test_dynamic_workflow_deterministic_id(client: TestClient):
    """workflow_id must be derived deterministically from chat_id + message_id."""
    import hashlib
    import uuid

    chat_id = f"det_chat_{uuid.uuid4().hex[:8]}"
    message_id = f"det_msg_{uuid.uuid4().hex[:8]}"
    base_payload = {
        "query": "Compute 2+2 with a simple script that prints the result only.",
        "use_workflow": True,
        "chat_id": chat_id,
        "message_id": message_id,
        "model_selection": get_model_selection(),
    }
    hash_input = f"{chat_id}:{message_id}".encode("utf-8")
    expected_wf = f"wf_{hashlib.md5(hash_input).hexdigest()[:12]}"

    events = _collect_workflow_events(client, base_payload, auto_confirm_message_id=message_id)
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
