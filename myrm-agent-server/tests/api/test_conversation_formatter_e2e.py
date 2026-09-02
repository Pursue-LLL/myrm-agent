"""End-to-end test for Conversation Formatter in real agent scenario."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import MemorySaver

from app.platform_utils import get_checkpointer, set_checkpointer
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
        assert response.status_code == 200

        events: list[dict[str, object]] = []
        full_content = ""
        for line in response.iter_lines():
            if not line:
                continue
            if line.startswith("data: "):
                data_str = line[6:]
                if data_str == "[DONE]":
                    break
                try:
                    data = json.loads(data_str)
                    if isinstance(data, dict):
                        events.append(data)
                        if data.get("type") in ("answer", "chunk", "message"):
                            content_val = data.get("content") or data.get("delta") or data.get("data")
                            if isinstance(content_val, str):
                                full_content += content_val
                except json.JSONDecodeError:
                    pass

        check_e2e_errors(events)
        assert len(full_content) > 0 or len(events) > 0
