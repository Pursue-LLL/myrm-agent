"""E2E Test for Dynamic Workflow Engine

This test verifies that sending a request with `use_workflow=True`
correctly routes to the Dynamic Workflow Engine, bypassing the standard
agent pipeline, and yields the expected workflow status events.
"""

import pytest
import json
from fastapi.testclient import TestClient

from tests.api.agent.utils import check_e2e_errors

def test_dynamic_workflow_e2e(client: TestClient):
    """Test that use_workflow=True triggers the dynamic workflow engine."""
    query = "Please analyze the codebase and write a summary."
    
    payload = {
        "query": query,
        "use_workflow": True,
        "chat_id": "test_chat_123",
        "message_id": "test_msg_456",
        "user_instructions": "Be concise.",
        "model_selection": {"provider": "openai", "model": "gpt-4o-mini"},
    }
    
    with client.stream("POST", "/api/v1/agents/agent-stream", json=payload) as response:
        assert response.status_code == 200
        
        collected_data = []
        for line in response.iter_lines():
            if not line or not line.startswith("data: "):
                continue
            try:
                data = json.loads(line[6:])
                collected_data.append(data)
            except json.JSONDecodeError:
                pass
                    
    assert len(collected_data) > 0, "Should have events"
    
    check_e2e_errors(collected_data)
    
    # Verify we got workflow-specific status events
    status_events = [d for d in collected_data if d.get("type") == "status"]
    
    step_keys = [d.get("step_key") for d in status_events]
    
    assert "workflow_init" in step_keys, "Missing workflow_init step"
    assert "workflow_planning" in step_keys, "Missing workflow_planning step"
    assert "workflow_execution" in step_keys, "Missing workflow_execution step"
    
    # Verify the final message contains evidence of the workflow execution
    content_events = [d for d in collected_data if d.get("type") == "content"]
    assert len(content_events) > 0, "Missing final content"
    
    final_content = "".join(d.get("content", "") for d in content_events)
    assert "Dynamic Workflow" in final_content
    assert "wf_" in final_content # The workflow ID
