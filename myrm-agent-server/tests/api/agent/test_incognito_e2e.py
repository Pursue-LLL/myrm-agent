"""Incognito mode full E2E: verifies read-only memory in streaming agent response.

Test scenarios:
1. incognito=True + enable_memory=True → 200 OK, stream completes without error
2. Verify no memory_save/memory_manage tool invocations in the response stream
"""

import json

from fastapi.testclient import TestClient

from tests.api.agent.utils import check_e2e_errors, get_model_selection


def test_incognito_mode_stream(client: TestClient):
    """Basic incognito stream must return 200 and complete without errors."""
    model_selection = get_model_selection()
    search_request = {
        "query": "hello incognito",
        "message_id": "test-msg-id",
        "chat_id": "test_incognito_e2e",
        "action_mode": "fast",
        "search_depth": "normal",
        "model_selection": model_selection,
        "enable_memory": True,
        "incognito_mode": True,
        "timezone": "UTC",
    }

    collected_data: list[dict[str, object]] = []
    with client.stream("POST", "/api/v1/agents/agent-stream", json=search_request) as response:
        assert response.status_code == 200
        for line in response.iter_lines():
            if line and line.strip().startswith("data: "):
                try:
                    data = json.loads(line.strip()[6:])
                    if isinstance(data, dict):
                        collected_data.append(data)
                except json.JSONDecodeError:
                    pass

    check_e2e_errors(collected_data)


def test_incognito_no_write_tools_in_stream(client: TestClient):
    """In incognito mode, memory_save and memory_manage must NOT appear in tool calls."""
    model_selection = get_model_selection()
    search_request = {
        "query": "Remember that my favorite color is blue",
        "message_id": "test-msg-incognito-no-write",
        "chat_id": "test_incognito_no_write",
        "action_mode": "fast",
        "search_depth": "normal",
        "model_selection": model_selection,
        "enable_memory": True,
        "incognito_mode": True,
        "timezone": "UTC",
    }

    collected_data: list[dict[str, object]] = []
    with client.stream("POST", "/api/v1/agents/agent-stream", json=search_request) as response:
        assert response.status_code == 200
        for line in response.iter_lines():
            if line and line.strip().startswith("data: "):
                try:
                    data = json.loads(line.strip()[6:])
                    if isinstance(data, dict):
                        collected_data.append(data)
                except json.JSONDecodeError:
                    pass

    check_e2e_errors(collected_data)

    blob = json.dumps(collected_data, ensure_ascii=False, default=str)
    assert "memory_save_tool" not in blob, "memory_save_tool should not be available in incognito mode"
    assert "memory_manage_tool" not in blob, "memory_manage_tool should not be available in incognito mode"
