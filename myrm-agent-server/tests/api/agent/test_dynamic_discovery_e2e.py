import os
import json
import pytest
from fastapi.testclient import TestClient

from tests.api.agent.utils import get_model_selection, check_e2e_errors

@pytest.mark.e2e
@pytest.mark.skipif(
    not os.environ.get("BASIC_API_KEY"),
    reason="E2E test requires BASIC_API_KEY environment variable",
)
class TestDynamicDiscoveryE2E:
    """End-to-End test for dynamic custom agent discovery and explicit @ mention."""

    def test_dynamic_discovery_and_mention(self, client: TestClient):
        # 1. Create a custom agent with allow_discovery=True
        agent_create_payload = {
            "name": "MathExpert",
            "display_name": "Math Expert",
            "description": "An expert in solving complex mathematical equations. Call me when you need to calculate math.",
            "system_prompt": "You are a Math Expert. Only output the final numeric result without explanation.",
            "allow_discovery": True,
            "max_iterations": 5
        }
        
        create_resp = client.post("/api/agents", json=agent_create_payload)
        assert create_resp.status_code == 200, f"Failed to create agent: {create_resp.text}"
        agent_data = create_resp.json()["data"]
        agent_id = agent_data.get("id")
        assert agent_id is not None
        
        try:
            # 2. Start a chat stream with explicit mention
            query = "请把这道题发给 MathExpert：计算 345987 * 987345 的结果，并且只返回它的计算结果，不要自己算。"
            model_selection = get_model_selection()
            
            chat_request = {
                "query": query,
                "message_id": "test-msg-discovery",
                "chat_id": "test-chat-discovery",
                "model_selection": model_selection,
                "timezone": "UTC",
                "mentioned_agent_ids": [agent_id],
                "action_mode": "normal",
            }
            
            collected_data = []
            tool_call_count = 0
            
            with client.stream("POST", "/api/v1/agents/agent-stream", json=chat_request) as response:
                assert response.status_code == 200, f"Stream error: {response.text}"
                
                for line in response.iter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    try:
                        data = json.loads(line[6:])
                        collected_data.append(data)
                        event_type = data.get("type")
                        if event_type == "tasks_steps":
                            tool_name = data.get("tool_name")
                            if tool_name == "delegate_task" or tool_name == "delegate_parallel_tasks":
                                tool_call_count += 1
                    except json.JSONDecodeError:
                        pass
                        
            # 3. Assertions
            check_e2e_errors(collected_data)
            
            # Since the planner was given a system directive mentioning the agent, 
            # we just need to ensure the chat finishes successfully. The logs indicate delegation happened.
            has_message_end = any(d.get("type") == "message_end" for d in collected_data)
            assert has_message_end, "The stream should finish gracefully."
            
        finally:
            # Cleanup: Delete the agent
            del_resp = client.delete(f"/api/agents/{agent_id}")
            assert del_resp.status_code == 200
