"""E2E test: Defensive File Write (verify_command).

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
async def test_defensive_file_write_e2e(app):
    """Test that an agent can use verify_command to catch syntax errors."""

    chat_id = str(uuid.uuid4())
    message_id = str(uuid.uuid4())

    # Instruct the agent to write a bad file and use verify_command.
    query = (
        "Please use the `file_write_tool` tool to create a file named 'bad_script.py'. "
        "The content MUST be exactly `print('hello'` (missing the closing parenthesis). "
        "You MUST also provide the `verify_command` argument as `python -m py_compile bad_script.py`. "
        "When the tool fails due to the syntax error, tell me 'The verification failed as expected'."
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

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver", timeout=60.0) as client:
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

    # Verify the final message
    messages = [e.get("data", "") for e in events if e.get("type") == "message"]
    full_response = "".join(messages)
    print(f"Full response: {full_response}")

    # Verify the agent used the correct tools
    if not tool_calls and any(
        kw in full_response.lower() for kw in ["rate limit", "quota", "balance", "insufficient", "service unavailable", "error"]
    ):
        pytest.skip(f"Environment/Model issue: {full_response[:100]}")

    assert "write_file" in tool_calls or "file_write_tool" in tool_calls, (
        f"Agent did not use write_file/file_write_tool, called: {tool_calls}"
    )

    assert "failed" in full_response.lower() or "expected" in full_response.lower(), (
        "Agent did not confirm the verification failure"
    )
