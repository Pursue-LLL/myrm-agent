"""TEMP diagnostic (will delete): verify render_ui with bindings+data emits ui_update SSE."""

from __future__ import annotations

import os
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from tests.api.agent.test_capability_gap_integration import _collect_agent_stream
from tests.api.agent.utils import check_e2e_errors, get_lite_model_selection


@pytest.mark.e2e
@pytest.mark.skipif(
    not os.environ.get("LITE_API_KEY") and not os.environ.get("BASIC_API_KEY"),
    reason="E2E test requires LITE_API_KEY or BASIC_API_KEY",
)
def test_tmp_ui_bindings_data_emits_ui_update(
    client: TestClient,
    mock_load_user_configs: pytest.AsyncMock,
) -> None:
    configs = mock_load_user_configs.return_value
    configs.security_config_dict = {
        **(configs.security_config_dict or {}),
        "yoloModeEnabled": True,
        "yolo_mode_enabled_at": time.time(),
    }

    chat_id = f"test_tmp_ui_bind_{uuid.uuid4().hex[:8]}"
    create_response = client.post("/api/v1/chats/", json={"chat_id": chat_id})
    assert create_response.status_code == 200

    query = (
        "Call render_ui_tool exactly once. Required arguments: "
        'title="E2E_UPDATE_MARKER_ALPHA"; '
        'components=[{"id":"s1","type":"text","props":{"variant":"body"},'
        '"bindings":{"text":"$.status"}}]; '
        'root_ids=["s1"]; data={"status":"E2E_UPDATE_INITIAL"}. '
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
        render_steps = [
            e
            for e in last_events
            if e.get("type") == "tasks_steps" and e.get("tool_name") == "render_ui_tool"
        ]
        ui_events = [
            e
            for e in last_events
            if e.get("type") == "ui_update" and e.get("subtype") == "ui_artifact"
        ]
        if ui_events:
            break

    assert render_steps, "Expected tasks_steps for render_ui_tool"
    assert ui_events, (
        f"Expected ui_update; render_steps={len(render_steps)}; "
        f"types={sorted({e.get('type') for e in last_events if isinstance(e.get('type'), str)})}"
    )

    data = ui_events[0].get("data")
    assert isinstance(data, list) and len(data) >= 1
    artifact = data[0]
    assert isinstance(artifact, dict)
    assert artifact.get("title") == "E2E_UPDATE_MARKER_ALPHA"
    assert artifact.get("data") == {"status": "E2E_UPDATE_INITIAL"}, (
        f"artifact.data mismatch: {artifact.get('data')!r}"
    )
    comps = artifact.get("components", [])
    assert comps, "expected components"
    first = comps[0]
    assert first.get("bindings") == {"text": "$.status"}, f"bindings mismatch: {first.get('bindings')!r}"
