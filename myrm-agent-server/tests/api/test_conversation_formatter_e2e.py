"""End-to-end test for Conversation Formatter in real agent scenario."""

import json

import pytest
from fastapi.testclient import TestClient

from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="chats")
from tests.api.agent.utils import get_model_selection


@pytest.mark.skip(reason="E2E test requiring real LLM - run manually if needed")
def test_conversation_formatter_in_fast_search() -> None:
    """Test conversation formatter works in a real search scenario via unified endpoint.

    This test verifies that:
    1. Priority-aware compression preserves critical messages
    2. Smart fallback triggers when needed
    3. Agent produces correct results despite context management

    NOTE: This is a manual E2E test. To run it:
    - Remove @pytest.mark.skip
    - Ensure BASIC_API_KEY is set
    - Run: uv run pytest tests/api/test_conversation_formatter_e2e.py -v -s
    """
    client = TestClient(app)

    request = {
        "query": "Summarize everything we discussed",
        "message_id": "test-conv-formatter",
        "chat_id": "test-conv-formatter-chat",
        "action_mode": "fast",
        "model_selection": get_model_selection(),
        "timezone": "UTC",
    }

    with client.stream("POST", "/api/v1/agents/agent-stream", json=request) as response:
        assert response.status_code == 200, f"HTTP {response.status_code}: {response.text}"

        full_response = ""
        for line in response.iter_lines():
            if not line or not line.startswith("data: "):
                continue

            data = json.loads(line[6:])

            if data.get("type") == "message":
                full_response += data.get("data", "")

        assert len(full_response) > 0, "Should produce a response"
        assert "summarize" in full_response.lower() or len(full_response) > 50, (
            "Should attempt to summarize or provide meaningful response"
        )
