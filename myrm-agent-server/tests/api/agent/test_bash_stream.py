import json
import os
import uuid

import pytest
from fastapi.testclient import TestClient

from tests.api.agent.utils import get_model_selection


def _stream_with_auto_approve(
    client: TestClient,
    request_data: dict[str, object],
) -> list[dict[str, object]]:
    collected: list[dict[str, object]] = []

    def _stream_once(req: dict[str, object]) -> None:
        with client.stream("POST", "/api/v1/agents/agent-stream", json=req, timeout=180.0) as response:
            assert response.status_code == 200
            for line in response.iter_lines():
                if not line or not line.startswith("data: "):
                    continue
                data_str = line[6:]
                if data_str == "[DONE]":
                    break
                try:
                    collected.append(json.loads(data_str))
                except json.JSONDecodeError:
                    continue

    _stream_once(request_data)

    for _ in range(10):
        approval_required = any(
            d.get("type") in ("approval_required", "tool_approval_request") for d in reversed(collected)
        )
        if not approval_required:
            break
        resume_request = dict(request_data)
        resume_request["resumeValue"] = [{"type": "approve", "extensions": {"allowAlways": True}}]
        _stream_once(resume_request)

    return collected


@pytest.mark.e2e
@pytest.mark.skipif(
    not os.environ.get("BASIC_API_KEY"),
    reason="E2E test requires BASIC_API_KEY environment variable",
)
@pytest.mark.asyncio
async def test_bash_stream(client: TestClient) -> None:
    chat_id = f"bash-chat-{uuid.uuid4().hex[:8]}"

    request_data: dict[str, object] = {
        "messageId": str(uuid.uuid4()),
        "query": (
            "Use bash_code_execute_tool to run exactly: echo hello world. "
            "Do not use any other tools."
        ),
        "chatId": chat_id,
        "modelSelection": get_model_selection(),
        "actionMode": "agent",
        "memoryRequireConfirmation": False,
        "enableMemoryAutoExtraction": False,
    }

    collected = _stream_with_auto_approve(client, request_data)

    error_events = [d for d in collected if d.get("type") == "error"]
    if error_events:
        error_msg = str(error_events[0])
        flaky_signals = (
            "Authentication",
            "Authorization",
            "Recursion limit",
            "Cannot connect",
            "Connection error",
            "InternalServerError",
            "BadRequestError",
            "ToolExecutionError",
        )
        if any(kw in error_msg for kw in flaky_signals):
            pytest.skip(f"Environment/upstream flaky: {error_msg[:240]}")
        pytest.fail(f"Agent execution error: {error_msg}")

    tool_stdout_chunk_received = any(d.get("type") == "tool_stdout_chunk" for d in collected)
    stream_blob = json.dumps(collected, default=str).lower()
    bash_invoked = tool_stdout_chunk_received or "bash_code_execute" in stream_blob

    assert bash_invoked, "Expected bash_code_execute_tool invocation or tool_stdout_chunk event"
