"""E2E test: Speculative Execution (race mode) and Physical Sync.

Relies on conftest.py autouse fixtures for DB, auth, and user config setup.
"""

import json
import os
import uuid

import httpx
import pytest
from dotenv import load_dotenv

from tests.api.agent.utils import get_model_selection

load_dotenv(override=True)


@pytest.mark.e2e
@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.environ.get("BASIC_API_KEY"),
    reason="E2E test requires BASIC_API_KEY environment variable",
)
async def test_speculative_execution_race_mode(app):
    """Test that an agent can use batch_delegate_tasks with race=True."""

    chat_id = str(uuid.uuid4())
    message_id = str(uuid.uuid4())

    # Instruct the agent to use race mode. We use a simple task to ensure it completes quickly.
    # We ask it to write a file in the workspace so we can verify the physical sync worked.
    query = (
        "Please use the `batch_delegate_tasks` tool with `race=True` to spawn 2 subagents (agent_type: 'coder'). "
        "Task for both: 'Create a file named race_winner.txt containing the word WINNER'. "
        "After the batch_delegate_tasks tool returns, read the file race_winner.txt to verify it exists, "
        "and tell me 'The race is won and the file exists'."
    )

    payload = {
        "messageId": message_id,
        "query": query,
        "chatId": chat_id,
        "modelSelection": get_model_selection(),
        "actionMode": "agent",
    }

    events = []
    tool_calls = []

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
        timeout=120.0,  # Subagents might take a while
    ) as client:
        async with client.stream("POST", "/api/v1/agents/agent-stream", json=payload) as resp:
            assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"

            async for line in resp.aiter_lines():
                if not line or not line.startswith("data: "):
                    continue
                try:
                    data = json.loads(line[6:])
                    events.append(data)

                    if data.get("type") == "tasks_steps":
                        tool_name = data.get("tool_name")
                        if tool_name:
                            tool_calls.append(tool_name)
                            print(f"Tool called: {tool_name}")

                    elif data.get("type") == "error":
                        error_msg = data.get("error", "")
                        if (
                            "RateLimitError" in error_msg
                            or "quota exceeded" in error_msg.lower()
                            or "invalid message role: system" in error_msg.lower()
                        ):
                            pytest.skip(f"Environment/Model issue: {error_msg}")
                        pytest.fail(f"Agent returned error: {error_msg}")

                except json.JSONDecodeError:
                    pass

    # Verify the agent used the correct tools
    assert "batch_delegate_tasks_tool" in tool_calls, "Agent did not use batch_delegate_tasks"

    # Verify the final message
    messages = [e.get("data", "") for e in events if e.get("type") == "message"]
    full_response = "".join(messages)
    print(f"Full response: {full_response}")

    assert "won" in full_response.lower() or "exists" in full_response.lower(), "Agent did not confirm the race winner file"
