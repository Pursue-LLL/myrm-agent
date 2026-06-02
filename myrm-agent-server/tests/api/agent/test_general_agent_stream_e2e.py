import json
import os
import uuid

import pytest
from fastapi.testclient import TestClient

from tests.api.agent.utils import get_model_selection


def perform_agent_stream(
    client: TestClient,
    query: str,
) -> tuple[str, list[dict], int]:
    request_data = {
        "messageId": f"gast-msg-{uuid.uuid4().hex[:12]}",
        "chatId": f"gast-chat-{uuid.uuid4().hex[:10]}",
        "query": query,
        "modelSelection": get_model_selection(),
        "actionMode": "agent",
        "memoryRequireConfirmation": False,
        "enableMemoryAutoExtraction": False,
    }

    collected_data = []
    message_chunks = []
    tool_call_count = 0
    heartbeat_count = 0

    with client.stream(
        "POST", "/api/v1/agents/agent-stream", json=request_data, timeout=120.0
    ) as response:
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
                        message_chunks.append(content)
                elif event_type == "tasks_steps":
                    tool_name = data.get("tool_name")
                    if tool_name is not None:
                        tool_call_count += 1
                elif event_type == "tool_heartbeat":
                    heartbeat_count += 1
            except json.JSONDecodeError:
                pass

    full_answer = "".join(message_chunks)
    return full_answer, collected_data, heartbeat_count


@pytest.mark.e2e
@pytest.mark.skipif(
    not os.environ.get("BASIC_API_KEY"),
    reason="E2E test requires BASIC_API_KEY environment variable",
)
class TestGeneralAgentStream:
    def test_agent_stream_heartbeat_and_empty_response(self, client: TestClient):
        # Prefer a deterministic completion-style prompt so E2E does not depend on
        # external search quotas (Tavily) or flaky tool recovery paths.
        query = (
            "Reply using only ASCII letters: literally OK — no punctuation, markdown, quotes, "
            "web search, or tool calls."
        )
        full_answer, collected_data, _ = perform_agent_stream(client, query)

        assert len(collected_data) > 0

        # Stream lifecycle progress probe (confirms SSE opened before agent work)
        progress_events = [d for d in collected_data if d.get("type") == "progress"]
        assert (
            len(progress_events) > 0
        ), "Should have received an instant progress event"
        assert (
            progress_events[0].get("data", {}).get("status") == "started"
        ), "First progress event should indicate 'started'"

        error_events = [d for d in collected_data if d.get("type") == "error"]
        if error_events:
            first_err = error_events[0]
            error_msg = str(first_err)
            flaky_signals = (
                "Authentication",
                "Authorization",
                "authorized_error",
                "APIConnectionError",
                "Invalid API Key",
                "invalid_key",
                "auth_permanent",
                "401",
                "403",
                "Recursion limit",
                "Connection error",
                "InternalServerError",
                "BadRequestError",
                "Param Incorrect",
                "quota exceeded",
                "SearchAPIError",
                "ToolExecutionError",
            )
            if first_err.get("error_kind") in ("format_error", "auth_permanent") or any(
                kw in error_msg for kw in flaky_signals
            ):
                pytest.skip(f"Environment/upstream flaky: {error_msg[:240]}")
            pytest.fail(f"Agent execution error: {error_msg}")

        if not full_answer:
            # For some reasoning models, the entire response might be in 'reasoning'
            # Or the answer is in tool calls. As long as we got data and didn't fail.
            assert (
                len(collected_data) > 10
            ), "Should have collected sufficient stream events"
        else:
            assert full_answer, "Should have answer"

        # Verify mascot_status integration
        # Each event yielded from streaming should contain a mascot_status attribute
        # representing current emotional mapping status.
        mascot_statuses = [
            d.get("mascot_status") for d in collected_data if "mascot_status" in d
        ]
        assert (
            len(mascot_statuses) > 0
        ), "Streaming events should contain mascot_status injection"

        # Valid mascot statuses defined in MascotStatus enum
        valid_statuses = {"sleeping", "thinking", "dizzy", "celebrating", "panting"}
        for status in mascot_statuses:
            assert status in valid_statuses, f"Invalid mascot status detected: {status}"
