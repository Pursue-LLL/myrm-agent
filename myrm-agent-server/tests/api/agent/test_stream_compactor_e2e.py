"""E2E test: StreamCompactor SSE chunking behavior.

Validates that the SSE stream uses StreamCompactor to buffer small LLM tokens
into larger chunks (avg > 10 chars), improving frontend rendering efficiency.
"""

import json
import os
import uuid

import pytest
from fastapi.testclient import TestClient

from tests.api.agent.utils import get_model_selection


@pytest.mark.e2e
@pytest.mark.skipif(
    not os.environ.get("BASIC_API_KEY"),
    reason="E2E test requires BASIC_API_KEY environment variable",
)
def test_stream_compactor_e2e(client: TestClient):
    """Stream response chunks should be batched by StreamCompactor (avg > 10 chars)."""
    unique_id = str(uuid.uuid4())
    payload = {
        "query": "Please write a 100-word essay about AI.",
        "modelSelection": get_model_selection(),
        "chatId": f"test_chat_{unique_id}",
        "messageId": f"test_msg_{unique_id}",
        "actionMode": "agent",
    }

    with client.stream("POST", "/api/v1/agents/agent-stream", json=payload, timeout=120.0) as response:
        if response.status_code != 200:
            response.read()
            pytest.fail(f"Agent request failed ({response.status_code}): {response.text[:500]}")

        message_chunks: list[str] = []
        total_chars = 0

        for line in response.iter_lines():
            if not line or not line.startswith("data: "):
                continue
            data_str = line[6:]
            if data_str == "[DONE]":
                break
            try:
                event = json.loads(data_str)
                if event.get("type") == "message":
                    chunk = event.get("data", "")
                    message_chunks.append(chunk)
                    total_chars += len(chunk)
            except json.JSONDecodeError:
                pass

    assert len(message_chunks) > 0, "Expected at least one message chunk"
    assert total_chars > 50, f"Total chars too low: {total_chars}"

    avg_chunk_size = total_chars / len(message_chunks)
    assert avg_chunk_size > 10, f"Avg chunk size {avg_chunk_size:.1f} is too small — StreamCompactor may not be working"
