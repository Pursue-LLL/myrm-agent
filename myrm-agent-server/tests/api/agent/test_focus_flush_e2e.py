import json
import os
import uuid

import pytest
from starlette.testclient import TestClient

from tests.api.agent.utils import get_model_selection


def test_focus_flush_session_with_real_model(client: TestClient):
    """
    E2E Test for Intelligent Session Focus & Flush feature with REAL MODEL.
    Verifies that:
    1. We can chat with the model.
    2. Messages are saved.
    3. Focus API clears the messages properly.
    4. Next chat starts fresh without previous context but in same chat_id.
    """

    # We require a real model to run this test properly
    if not os.getenv("BASIC_API_KEY") and not os.getenv("OPENAI_API_KEY") and not os.getenv("ANTHROPIC_API_KEY"):
        pytest.skip("Skipping real model E2E test due to missing API keys.")

    chat_id = f"test_chat_focus_{uuid.uuid4().hex[:8]}"

    # 1. Create a new chat
    create_response = client.post("/api/v1/chats/", json={"chat_id": chat_id})
    assert create_response.status_code == 200

    # 2. Chat with the real model
    request_data = {
        "messageId": f"msg_1_{uuid.uuid4().hex[:8]}",
        "chatId": chat_id,
        "query": "Remember this secret code: 'FOCUS_TEST_999'. Reply 'Got it'.",
        "modelSelection": get_model_selection(),
    }

    full_response_1 = ""
    with client.stream("POST", "/api/v1/agents/agent-stream", json=request_data) as response:
        assert response.status_code == 200
        for line in response.iter_lines():
            if not line or not line.startswith("data: "):
                continue
            try:
                data = json.loads(line[6:])
                if data.get("type") in ("message", "reasoning"):
                    full_response_1 += data.get("data", "")
            except Exception:
                pass

    assert len(full_response_1) > 0, "Model should return a response"

    # 3. Call the Focus & Flush API
    flush_response = client.delete(f"/api/v1/chats/{chat_id}/messages")
    assert flush_response.status_code == 200
    assert flush_response.json()["data"]["cleared"] is True

    # 4. Ask the model for the secret code to verify it has been cleared
    request_data_2 = {
        "messageId": f"msg_2_{uuid.uuid4().hex[:8]}",
        "chatId": chat_id,
        "query": "What was the secret code I just told you? If you don't know, reply exactly with 'I don't know'.",
        "modelSelection": get_model_selection(),
    }

    full_response_2 = ""
    with client.stream("POST", "/api/v1/agents/agent-stream", json=request_data_2) as response:
        assert response.status_code == 200
        for line in response.iter_lines():
            if not line or not line.startswith("data: "):
                continue
            try:
                data = json.loads(line[6:])
                if data.get("type") in ("message", "reasoning"):
                    full_response_2 += data.get("data", "")
            except Exception:
                pass

    assert len(full_response_2) > 0, "Model should return a response"

    # Assert that the context was cleared, so it shouldn't know the code
    assert "FOCUS_TEST_999" not in full_response_2, f"Model remembered the secret after focus/flush! Response: {full_response_2}"
