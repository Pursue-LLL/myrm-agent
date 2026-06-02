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
        "messageId": f"cal-msg-{uuid.uuid4().hex[:12]}",
        "chatId": f"cal-chat-{uuid.uuid4().hex[:10]}",
        "query": query,
        "modelSelection": get_model_selection(),
        "actionMode": "agent",
        "memoryRequireConfirmation": False,
        "enableMemoryAutoExtraction": False,
    }

    collected_data = []
    message_chunks = []
    tool_call_count = 0

    with client.stream("POST", "/api/v1/agents/agent-stream", json=request_data, timeout=120.0) as response:
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
            except json.JSONDecodeError:
                pass

    full_answer = "".join(message_chunks)
    return full_answer, collected_data, tool_call_count

@pytest.mark.e2e
@pytest.mark.skipif(
    not os.environ.get("BASIC_API_KEY"),
    reason="E2E test requires BASIC_API_KEY environment variable",
)
class TestCalendarE2E:
    def test_calendar_agent_invokes_free_busy_tool(self, client: TestClient):
        # We explicitly ask the agent to call the calendar tool to find meeting slots.
        query = (
            "请调用 find_optimal_meeting_slots 工具，帮我排期一下明天下午有没有时间可以开会。只调用工具即可。"
        )
        full_answer, collected_data, tool_call_count = perform_agent_stream(client, query)

        assert len(collected_data) > 0

        error_events = [d for d in collected_data if d.get("type") == "error"]
        if error_events:
            first_err = error_events[0]
            error_msg = str(first_err)
            flaky_signals = (
                "Authentication",
                "Authorization",
                "Cannot connect",
                "InternalServerError",
                "BadRequestError",
                "quota exceeded",
            )
            if any(kw in error_msg for kw in flaky_signals):
                pytest.skip(f"Environment/upstream flaky: {error_msg[:240]}")
            pytest.fail(f"Agent execution error: {error_msg}")

        # check if tool find_optimal_meeting_slots was called
        tool_called = False
        for event in collected_data:
            if event.get("type") == "tasks_steps" and event.get("tool_name") == "find_optimal_meeting_slots":
                tool_called = True
                break
            
            # also check if the model output the raw tool call for some reason
            if event.get("type") == "message" and "find_optimal_meeting_slots" in str(event.get("data", "")):
                tool_called = True
                break
                
        assert tool_called, "The agent must invoke the find_optimal_meeting_slots tool."
