import json
import os
import uuid

import pytest
from starlette.testclient import TestClient

from tests.api.agent.utils import get_model_selection


@pytest.mark.asyncio
async def test_goal_acceptance_e2e_real_model(client: TestClient):
    """
    E2E Test for Goal Acceptance Criteria with REAL MODEL.
    Verifies that:
    1. A goal can be created with shell acceptance criteria.
    2. The agent correctly works to satisfy the criteria and updates the status to complete.
    3. The gatekeeper verifies the outcome.
    """
    if (
        not os.getenv("BASIC_API_KEY")
        and not os.getenv("OPENAI_API_KEY")
        and not os.getenv("ANTHROPIC_API_KEY")
    ):
        pytest.skip("Skipping real model E2E test due to missing API keys.")

    chat_id = f"test_goal_e2e_{uuid.uuid4().hex[:8]}"

    # 1. Create a new chat
    create_response = client.post("/api/v1/chats/", json={"chat_id": chat_id})
    assert create_response.status_code == 200

    # 2. Chat with the real model, setting a goal with acceptance criteria
    request_data = {
        "messageId": f"msg_1_{uuid.uuid4().hex[:8]}",
        "chatId": chat_id,
        "query": "Please call the `update_goal_status` tool with status 'complete'. You do not need to do any actual work, just call the tool.",
        "modelSelection": get_model_selection(),
        "goal": {
            "objective": "Just complete the goal",
                "maxTokens": 100000,
            "acceptance_criteria": [
                {
                    "type": "shell",
                    "command": "echo 'Hello World'",
                    "timeout_seconds": 60
                }
            ]
        }
    }

    full_response = ""
    tool_calls = []
    
    with client.stream(
        "POST", "/api/v1/agents/agent-stream", json=request_data
    ) as response:
        assert response.status_code == 200
        for line in response.iter_lines():
            if not line or not line.startswith("data: "):
                continue
            try:
                data = json.loads(line[6:])
                event_type = data.get("type")
                if event_type in ("message", "reasoning"):
                    full_response += data.get("data", "")
                elif event_type == "tasks_steps":
                    tool_name = data.get("tool_name")
                    if tool_name is not None:
                        tool_calls.append(tool_name)
            except Exception:
                pass

    # Verify that the agent successfully ran tools
    assert len(tool_calls) > 0, "Model should have called tools to complete the goal"
    
    # 3. Verify the goal status via API
    status_response = client.get(f"/api/v1/goals/{chat_id}/status")
    assert status_response.status_code == 200
    goal_data = status_response.json().get("goal")
    
    assert goal_data is not None, "Goal should exist"
    assert goal_data["status"] == "complete", f"Goal should be marked complete, but got {goal_data['status']}"
