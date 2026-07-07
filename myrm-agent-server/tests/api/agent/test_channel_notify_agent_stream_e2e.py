"""E2E: agent-stream with notify_targets must invoke channel_notify_tool and deliver to chat."""

from __future__ import annotations

import os
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from tests.api.agent.test_capability_gap_integration import (
    _collect_agent_stream,
    _invoked_tool_names,
)
from tests.api.agent.utils import check_e2e_errors, get_model_selection


NOTIFY_BODY = "E2E integration test"


def _notify_tool_steps(events: list[dict[str, object]]) -> list[dict[str, object]]:
    return [
        event
        for event in events
        if event.get("type") == "tasks_steps" and event.get("tool_name") == "channel_notify_tool"
    ]


@pytest.mark.e2e
@pytest.mark.skipif(
    not os.environ.get("BASIC_API_KEY") and not os.environ.get("LITE_API_KEY"),
    reason="E2E test requires BASIC_API_KEY or LITE_API_KEY",
)
def test_agent_stream_channel_notify_delivers_to_chat(
    client: TestClient,
    mock_load_user_configs: pytest.AsyncMock,
) -> None:
    """Real agent-stream: channel_notify_tool must deliver to configured chat recipient."""
    configs = mock_load_user_configs.return_value
    configs.security_config_dict = {
        **(configs.security_config_dict or {}),
        "yoloModeEnabled": True,
        "yolo_mode_enabled_at": time.time(),
    }

    recipient_chat_id = f"notify_recipient_{uuid.uuid4().hex[:8]}"
    create_agent = client.post(
        "/api/agents",
        json={
            "name": "Channel Notify Stream E2E",
            "system_prompt": "You send notifications when asked.",
            "model_selection": get_model_selection(),
            "notify_targets": [
                {"channel": "chat", "recipient_id": recipient_chat_id, "label": "E2E Notify"},
            ],
        },
    )
    assert create_agent.status_code == 200, create_agent.text
    agent_id = create_agent.json()["data"]["id"]

    chat_id = f"test_notify_{uuid.uuid4().hex[:8]}"
    assert client.post("/api/v1/chats/", json={"chat_id": chat_id}).status_code == 200

    query = (
        "Call channel_notify_tool exactly once. "
        f'Send body "{NOTIFY_BODY}" to the configured chat target. '
        "Do not call any other tools. After success, reply NOTIFY_DONE."
    )

    notify_steps: list[dict[str, object]] = []
    last_events: list[dict[str, object]] = []

    try:
        for attempt in range(3):
            payload: dict[str, object] = {
                "messageId": f"msg_{uuid.uuid4().hex[:8]}",
                "chatId": chat_id,
                "query": query if attempt == 0 else f"[retry {attempt + 1}] {query}",
                "modelSelection": get_model_selection(),
                "actionMode": "agent",
                "agentId": agent_id,
                "enableMemory": False,
            }
            last_events = _collect_agent_stream(client, payload)
            check_e2e_errors(last_events)
            notify_steps = _notify_tool_steps(last_events)
            if notify_steps:
                break

        invoked = _invoked_tool_names(last_events)
        assert "channel_notify_tool" in invoked, f"Expected channel_notify_tool; got {sorted(invoked)}"
        assert notify_steps, "Expected tasks_steps for channel_notify_tool"

        messages_resp = client.get(f"/api/v1/chats/{recipient_chat_id}/messages")
        assert messages_resp.status_code == 200, messages_resp.text
        messages = messages_resp.json().get("data", {}).get("messages", [])
        delivered = [
            msg
            for msg in messages
            if isinstance(msg, dict)
            and isinstance(msg.get("content"), str)
            and NOTIFY_BODY in msg["content"]
        ]
        assert delivered, f"No delivered message in chat {recipient_chat_id}; messages={messages}"
    finally:
        client.delete(f"/api/agents/{agent_id}")
