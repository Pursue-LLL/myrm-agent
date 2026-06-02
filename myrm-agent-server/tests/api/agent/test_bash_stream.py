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
@pytest.mark.asyncio
async def test_bash_stream(client: TestClient) -> None:
    chat_id = f"bash-chat-{uuid.uuid4().hex[:8]}"

    request_data = {
        "messageId": str(uuid.uuid4()),
        "query": "Please use bash_exec to run 'echo hello world'. Do not do anything else.",
        "chatId": chat_id,
        "modelSelection": get_model_selection(),
        "actionMode": "agent",
    }

    tool_stdout_chunk_received = False

    with client.stream("POST", "/api/v1/agents/agent-stream", json=request_data) as response:
        assert response.status_code == 200
        for line in response.iter_lines():
            if not line:
                continue
            if line.startswith("data: "):
                data_str = line[6:]
                if data_str == "[DONE]":
                    break
                try:
                    event_data = json.loads(data_str)
                    print(f"EVENT TYPE: {event_data.get('type')}")
                    if event_data.get("type") == "tool_stdout_chunk":
                        tool_stdout_chunk_received = True
                        print(f"✅ Received tool_stdout_chunk event: {event_data}")
                except json.JSONDecodeError:
                    continue

    assert tool_stdout_chunk_received, "Expected 'tool_stdout_chunk' event was not received."
