"""E2E: agent-stream with render_ui enabled must emit UI_UPDATE when model invokes render_ui_tool."""

from __future__ import annotations

import os
import time
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


def _ui_artifact_events(events: list[dict[str, object]]) -> list[dict[str, object]]:
    return [
        event
        for event in events
        if event.get("type") == "ui_update" and event.get("subtype") == "ui_artifact"
    ]


@pytest.mark.e2e
@pytest.mark.skipif(
    not os.environ.get("LITE_API_KEY") and not os.environ.get("BASIC_API_KEY"),
    reason="E2E test requires LITE_API_KEY or BASIC_API_KEY",
)
def test_agent_stream_render_ui_emits_ui_update_sse(
    client: TestClient,
    mock_load_user_configs: pytest.AsyncMock,
) -> None:
    """Real agent-stream: render_ui_tool invocation must produce ui_update SSE with ui_artifact."""
    configs = mock_load_user_configs.return_value
    configs.security_config_dict = {
        **(configs.security_config_dict or {}),
        "yoloModeEnabled": True,
        "yolo_mode_enabled_at": time.time(),
    }

    chat_id = f"test_render_ui_{uuid.uuid4().hex[:8]}"
    create_response = client.post("/api/v1/chats/", json={"chat_id": chat_id})
    assert create_response.status_code == 200

    query = (
        "Call render_ui_tool exactly once. Required arguments: "
        'title="部署确认"; '
        'components=[{"id":"t1","type":"text","props":{"text":"确认重启 staging?"}}]; '
        'root_ids=["t1"]. '
        "Every component MUST include a type field. "
        "Do not use any other tools. After render_ui_tool succeeds, reply DONE."
    )

    ui_events: list[dict[str, object]] = []
    render_steps: list[dict[str, object]] = []
    last_events: list[dict[str, object]] = []

    for attempt in range(3):
        payload: dict[str, object] = {
            "messageId": f"msg_{uuid.uuid4().hex[:8]}",
            "chatId": chat_id,
            "query": query if attempt == 0 else f"[retry {attempt + 1}] {query}",
            "modelSelection": get_lite_model_selection(),
            "actionMode": "agent",
            "enableMemory": False,
            "agentConfig": {
                "enabledBuiltinTools": ["render_ui"],
            },
        }
        last_events = _collect_agent_stream(client, payload)
        check_e2e_errors(last_events)
        render_steps = _render_ui_tasks_steps(last_events)
        ui_events = _ui_artifact_events(last_events)
        if ui_events:
            break

    assert render_steps, "Expected tasks_steps events for render_ui_tool"
    assert ui_events, (
        f"Expected ui_update after render_ui_tool; render_steps={len(render_steps)}; "
        f"event_types={sorted({e.get('type') for e in last_events if isinstance(e.get('type'), str)})}"
    )

    data = ui_events[0].get("data")
    assert isinstance(data, list) and len(data) >= 1
    artifact = data[0]
    assert isinstance(artifact, dict)
    assert artifact.get("title") == "部署确认"
    assert len(artifact.get("components", [])) >= 1
    assert artifact.get("root_ids")
