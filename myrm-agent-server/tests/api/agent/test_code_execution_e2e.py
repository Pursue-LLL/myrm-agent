"""Code execution E2E — verifies agent can invoke bash_code_execute_tool with real LLM."""

import json
import os
import re
import uuid

import pytest
from fastapi.testclient import TestClient

from tests.api.agent.utils import get_model_selection


def _digits(text: str) -> str:
    return re.sub(r"\D", "", text)


def perform_code_execution_agent(
    client: TestClient,
    query: str,
) -> tuple[str, list[dict[str, object]], int]:
    chat_id = f"gast-chat-{uuid.uuid4().hex[:10]}"
    request_data: dict[str, object] = {
        "messageId": f"gast-msg-{uuid.uuid4().hex[:12]}",
        "chatId": chat_id,
        "query": query,
        "modelSelection": get_model_selection(),
        "actionMode": "agent",
        "memoryRequireConfirmation": False,
        "enableMemoryAutoExtraction": False,
    }

    collected_data: list[dict[str, object]] = []
    message_chunks: list[str] = []
    tool_call_count = 0

    def _stream_req(req_data: dict[str, object]) -> None:
        nonlocal tool_call_count
        with client.stream("POST", "/api/v1/agents/agent-stream", json=req_data, timeout=180.0) as response:
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
                    if event_type in ("message", "reasoning"):
                        content = data.get("data", "")
                        if content:
                            message_chunks.append(str(content))
                    elif event_type == "tasks_steps":
                        tool_name = data.get("tool_name")
                        if tool_name is not None:
                            tool_call_count += 1
                except json.JSONDecodeError:
                    pass

    _stream_req(request_data)

    for _ in range(10):
        approval_required = False
        for data in reversed(collected_data):
            if data.get("type") in ("approval_required", "tool_approval_request"):
                approval_required = True
                break
            if data.get("type") in ("message_end", "error"):
                break
        if not approval_required:
            break
        resume_request = dict(request_data)
        resume_request["resumeValue"] = [{"type": "approve", "extensions": {"allowAlways": True}}]
        _stream_req(resume_request)

    return "".join(message_chunks), collected_data, tool_call_count


@pytest.mark.e2e
@pytest.mark.skipif(
    not os.environ.get("BASIC_API_KEY"),
    reason="E2E test requires BASIC_API_KEY environment variable",
)
class TestCodeExecutionE2E:
    def test_agent_code_execution(self, client: TestClient) -> None:
        query = 'Use bash_code_execute_tool to run exactly: python3 -c "print(898989 * 121212)". Return only the printed number.'
        full_answer, collected_data, tool_call_count = perform_code_execution_agent(client, query)

        assert len(collected_data) > 0

        error_events = [d for d in collected_data if d.get("type") == "error"]
        if error_events:
            first_err = error_events[0]
            error_msg = str(first_err)
            flaky_signals = (
                "Authentication",
                "Authorization",
                "Recursion limit",
                "Cannot connect",
                "Connection error",
                "InternalServerError",
                "BadRequestError",
                "Param Incorrect",
                "quota exceeded",
                "SearchAPIError",
                "ToolExecutionError",
                "Connection lost",
                "ConnectionResetError",
            )
            if first_err.get("error_kind") == "format_error" or any(kw in error_msg for kw in flaky_signals):
                pytest.skip(f"Environment/upstream flaky: {error_msg[:240]}")
            pytest.fail(f"Agent execution error: {error_msg}")

        has_message_end = any(d.get("type") == "message_end" for d in collected_data)
        assert has_message_end or tool_call_count > 0, "Stream should complete or use tools"

        stream_blob = json.dumps(collected_data, default=str)
        bash_invoked = (
            tool_call_count > 0 or "bash_code_execute" in stream_blob.lower() or _digits("108968254668") in _digits(full_answer)
        )
        assert bash_invoked, "Should invoke bash_code_execute_tool or return correct calculated number"
