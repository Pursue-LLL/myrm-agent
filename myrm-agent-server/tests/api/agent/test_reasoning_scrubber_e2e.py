import json
import os
import uuid

import pytest
from fastapi.testclient import TestClient

from tests.api.agent.utils import check_e2e_errors, get_model_selection


@pytest.mark.e2e
@pytest.mark.skipif(
    not os.environ.get("BASIC_API_KEY"),
    reason="E2E test requires BASIC_API_KEY environment variable",
)
class TestReasoningScrubberE2E:
    """Verify reasoning content is properly separated from visible output.

    For thinking models (DeepSeek/MiMo/Kimi), reasoning arrives via the
    dedicated 'reasoning' event type and must never leak into 'message' events.
    For non-thinking models that emit <think> tags inline, the scrubber strips
    those tags from the visible message stream.
    """

    def test_reasoning_separated_from_message(self, client: TestClient):
        """Reasoning content (if any) must not appear in message chunks."""
        chat_id = f"test-chat-scrubber-{uuid.uuid4().hex[:8]}"
        request_data = {
            "messageId": f"msg-{uuid.uuid4().hex[:8]}",
            "chatId": chat_id,
            "query": "What is 2+2? Answer briefly.",
            "modelSelection": get_model_selection(),
        }

        collected_data: list[dict] = []
        reasoning_chunks: list[str] = []
        message_chunks: list[str] = []

        with client.stream("POST", "/api/v1/agents/agent-stream", json=request_data) as response:
            assert response.status_code == 200

            for line in response.iter_lines():
                if not line or not line.startswith("data: "):
                    continue
                try:
                    data = json.loads(line[6:])
                    if data is None:
                        continue
                    collected_data.append(data)
                    event_type = data.get("type", "unknown")

                    if event_type == "reasoning":
                        reasoning_chunks.append(data.get("data", ""))
                    elif event_type == "message":
                        message_chunks.append(data.get("data", ""))
                except json.JSONDecodeError:
                    pass

        check_e2e_errors(collected_data)

        full_message = "".join(message_chunks)

        assert full_message, "Agent must produce a non-empty answer"
        assert "<think>" not in full_message
        assert "</think>" not in full_message

        resp = client.get(f"/api/v1/chats/{chat_id}/messages")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        messages = data["data"]["messages"]

        assistant_msgs = [m for m in messages if m["role"] == "assistant"]
        assert assistant_msgs, "At least one assistant message must be persisted"
        content = assistant_msgs[-1]["content"]
        assert "<think>" not in content
        assert "</think>" not in content

    def test_multiturn_thinking_model_no_400(self, client: TestClient):
        """Multi-turn conversation with thinking model must not trigger 400.

        This validates the reasoning_content stamp: when ThinkingBlockCleaner
        removes reasoning_content from older messages, the stamp re-adds an
        empty string before sending to the API, preventing 400 errors.
        """
        chat_id = f"test-multiturn-stamp-{uuid.uuid4().hex[:8]}"

        req1 = {
            "messageId": f"msg-{uuid.uuid4().hex[:8]}",
            "chatId": chat_id,
            "query": "Hi, what is 1+1?",
            "modelSelection": get_model_selection(),
        }

        collected1: list[dict] = []
        with client.stream("POST", "/api/v1/agents/agent-stream", json=req1) as response:
            assert response.status_code == 200
            for line in response.iter_lines():
                if not line or not line.startswith("data: "):
                    continue
                try:
                    data = json.loads(line[6:])
                    if data:
                        collected1.append(data)
                except json.JSONDecodeError:
                    pass

        check_e2e_errors(collected1)
        msg1 = "".join(d.get("data", "") for d in collected1 if d.get("type") == "message")
        assert msg1, "Turn 1 must produce output"

        req2 = {
            "messageId": f"msg-{uuid.uuid4().hex[:8]}",
            "chatId": chat_id,
            "query": "And what is 2+2?",
            "modelSelection": get_model_selection(),
        }

        collected2: list[dict] = []
        with client.stream("POST", "/api/v1/agents/agent-stream", json=req2) as response:
            assert response.status_code == 200
            for line in response.iter_lines():
                if not line or not line.startswith("data: "):
                    continue
                try:
                    data = json.loads(line[6:])
                    if data:
                        collected2.append(data)
                except json.JSONDecodeError:
                    pass

        check_e2e_errors(collected2)
        msg2 = "".join(d.get("data", "") for d in collected2 if d.get("type") == "message")
        assert msg2, "Turn 2 must produce output (no 400 from missing reasoning_content)"

        errors2 = [d for d in collected2 if d.get("type") == "error"]
        for err in errors2:
            err_text = str(err.get("error", "") or err.get("data", ""))
            assert "reasoning_content" not in err_text.lower(), f"reasoning_content error in turn 2: {err_text}"
