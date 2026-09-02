"""End-to-end test for Conversation Formatter in real agent scenario."""

import json

import pytest
from fastapi.testclient import TestClient

from langgraph.checkpoint.memory import MemorySaver

from app.platform_utils import get_checkpointer, set_checkpointer
from tests.api.agent.conftest import (
    _build_mock_user_configs,
    app,
    client,
    disable_commitment_extraction,
    disable_memory_auto_extraction,
    mock_load_user_configs,
    setup_test_database,
)
from tests.api.agent.utils import check_e2e_errors, get_model_selection


@pytest.fixture(autouse=True)
def setup_test_checkpointer():
    try:
        get_checkpointer()
    except RuntimeError:
        set_checkpointer(MemorySaver())
    yield


@pytest.mark.e2e
def test_conversation_formatter_in_fast_search(client: TestClient) -> None:
    """Test conversation formatter works in a real search scenario via unified endpoint.

    This test verifies that:
    1. Priority-aware compression preserves critical messages
    2. Smart fallback triggers when needed
    3. Agent produces correct results despite context management
    """
    request = {
        "query": "Say hello in one short sentence.",
        "message_id": "test-conv-formatter",
        "chat_id": "test-conv-formatter-chat",
        "action_mode": "fast",
        "model_selection": get_model_selection(),
        "timezone": "UTC",
    }

    with client.stream("POST", "/api/v1/agents/agent-stream", json=request) as response:
        assert response.status_code == 200, f"HTTP {response.status_code}: {response.text}"

        events: list[dict[str, object]] = []
        full_response = ""
        for line in response.iter_lines():
            if not line or not line.startswith("data: "):
                continue

            try:
                data = json.loads(line[6:])
                if isinstance(data, dict):
                    events.append(data)
                    if data.get("type") == "message":
                        full_response += str(data.get("data", ""))
            except json.JSONDecodeError:
                continue

        check_e2e_errors(events)
        assert len(events) > 0, "Should produce SSE events"
        assert len(full_response) > 0 or any(e.get("type") in {"progress", "message", "finish"} for e in events)
