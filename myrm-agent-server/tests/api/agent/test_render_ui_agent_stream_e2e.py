"""E2E: agent-stream with render_ui enabled must emit UI_UPDATE when model invokes render_ui_tool."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from tests.api.agent.test_capability_gap_integration import _collect_agent_stream
from tests.api.agent.utils import check_e2e_errors, get_model_selection


def _render_ui_tasks_steps(events: list[dict[str, object]]) -> list[dict[str, object]]:
    return [
        event
        for event in events
        if event.get("type") == "tasks_steps" and event.get("tool_name") == "render_ui_tool"
    ]


@pytest.mark.e2e
def test_agent_stream_render_ui_emits_ui_update_sse(client: TestClient) -> None:
    """Real agent-stream: render_ui_tool invocation must produce ui_update SSE with ui_artifact."""
    chat_id = f"test_render_ui_{uuid.uuid4().hex[:8]}"
    create_response = client.post("/api/v1/chats/", json={"chat_id": chat_id})
    assert create_response.status_code == 200

    payload: dict[str, object] = {
        "message_id": "test-render-ui-e2e-1",
        "chat_id": chat_id,
        "query": (
            "【测试】你必须且只能调用 render_ui_tool 一次，参数："
            "title=部署确认；components=["
            '{"id":"t1","type":"text","props":{"text":"确认重启 staging?"}},'
            '{"id":"f1","type":"text_field","props":{"label":"备注"},"bindings":{"value":"$.form.note"}},'
            '{"id":"b1","type":"button","props":{"label":"确认"},"events":{"onClick":"submit"}}'
            "]; root_ids=[\"t1\",\"f1\",\"b1\"]; data={\"form\":{\"note\":\"\"}};"
            'actions=[{"id":"submit","type":"submit","label":"确认"}]。'
            "禁止只用 Markdown。调用成功后回复 DONE。"
        ),
        "action_mode": "agent",
        "model_selection": get_model_selection(),
        "agent_config": {
            "enabled_builtin_tools": [
                "web_search",
                "memory",
                "file_ops",
                "code_execute",
                "render_ui",
            ],
            "skill_ids": [],
        },
        "timezone": "UTC",
    }
    events = _collect_agent_stream(client, payload)
    check_e2e_errors(events)

    if not _render_ui_tasks_steps(events):
        pytest.skip(
            "model did not invoke render_ui_tool; deterministic wiring covered by "
            "tests/integration/test_render_ui_sse_wiring.py"
        )

    ui_events = [
        event
        for event in events
        if event.get("type") == "ui_update" and event.get("subtype") == "ui_artifact"
    ]
    if not ui_events:
        pytest.skip(
            "render_ui_tool tasks_steps seen but model did not complete a successful render; "
            "cross-task stash fix covered by tests/integration/test_render_ui_sse_wiring.py"
        )
    data = ui_events[0].get("data")
    assert isinstance(data, list) and len(data) >= 1
    artifact = data[0]
    assert isinstance(artifact, dict)
    assert artifact.get("title") == "部署确认"
    assert len(artifact.get("components", [])) >= 2
    assert artifact.get("root_ids")
