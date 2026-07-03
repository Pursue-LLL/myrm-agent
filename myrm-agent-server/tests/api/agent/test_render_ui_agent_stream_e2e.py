"""E2E: agent-stream with render_ui enabled must emit UI_UPDATE when model invokes render_ui_tool."""

from __future__ import annotations

import os
import uuid

import pytest
from fastapi.testclient import TestClient

from tests.api.agent.test_capability_gap_integration import _collect_agent_stream
from tests.api.agent.utils import check_e2e_errors, get_lite_model_selection


def _render_ui_tasks_steps(events: list[dict[str, object]]) -> list[dict[str, object]]:
    return [
        event
        for event in events
        if event.get("type") == "tasks_steps" and event.get("tool_name") == "render_ui_tool"
    ]


@pytest.mark.e2e
@pytest.mark.skipif(
    not os.environ.get("LITE_API_KEY") and not os.environ.get("BASIC_API_KEY"),
    reason="E2E test requires LITE_API_KEY or BASIC_API_KEY",
)
def test_agent_stream_render_ui_emits_ui_update_sse(client: TestClient) -> None:
    """Real agent-stream: render_ui_tool invocation must produce ui_update SSE with ui_artifact."""
    chat_id = f"test_render_ui_{uuid.uuid4().hex[:8]}"
    create_response = client.post("/api/v1/chats/", json={"chat_id": chat_id})
    assert create_response.status_code == 200

    payload: dict[str, object] = {
        "messageId": f"msg_{uuid.uuid4().hex[:8]}",
        "chatId": chat_id,
        "query": (
            "You MUST call render_ui_tool exactly once with: "
            'title="部署确认"; '
            'components=[{"id":"t1","type":"text","props":{"text":"确认重启 staging?"}},'
            '{"id":"f1","type":"text_field","props":{"label":"备注"},"bindings":{"value":"$.form.note"}},'
            '{"id":"b1","type":"button","props":{"label":"确认"},"events":{"onClick":"submit"}}]; '
            'root_ids=["t1","f1","b1"]; '
            'data={"form":{"note":""}}; '
            'actions=[{"id":"submit","type":"submit","label":"确认"}]. '
            "Do not use any other tools. After render_ui_tool succeeds, reply DONE."
        ),
        "modelSelection": get_lite_model_selection(),
        "actionMode": "agent",
        "agentConfig": {
            "enabledBuiltinTools": ["render_ui"],
        },
    }
    events = _collect_agent_stream(client, payload)
    check_e2e_errors(events)

    render_steps = _render_ui_tasks_steps(events)
    assert render_steps, "Expected tasks_steps events for render_ui_tool"

    ui_events = [
        event
        for event in events
        if event.get("type") == "ui_update" and event.get("subtype") == "ui_artifact"
    ]
    assert ui_events, (
        f"Expected ui_update after render_ui_tool; "
        f"render_steps={len(render_steps)}; "
        f"event_types={sorted({e.get('type') for e in events if isinstance(e.get('type'), str)})}"
    )

    data = ui_events[0].get("data")
    assert isinstance(data, list) and len(data) >= 1
    artifact = data[0]
    assert isinstance(artifact, dict)
    assert artifact.get("title") == "部署确认"
    assert len(artifact.get("components", [])) >= 2
    assert artifact.get("root_ids")
