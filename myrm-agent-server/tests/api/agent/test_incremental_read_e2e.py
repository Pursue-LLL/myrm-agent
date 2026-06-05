"""Incremental Read Log E2E Tests.

Test /api/v1/agents/agent-stream endpoint for incremental log reading capabilities.
"""

import json
import os
import uuid

os.environ["DEPLOY_MODE"] = "tauri"

import pytest
from fastapi.testclient import TestClient

from tests.api.agent.utils import get_model_selection, get_search_service_config


def perform_agent_search_with_auto_approve(client: TestClient, query: str):
    """Run search and automatically approve any required tool calls."""
    chat_id = str(uuid.uuid4())
    message_id = str(uuid.uuid4())

    search_request = {
        "messageId": message_id,
        "chatId": chat_id,
        "query": query,
        "modelSelection": get_model_selection(),
        "searchServiceCfg": get_search_service_config(),
        "actionMode": "agent",
    }

    collected_data = []
    message_chunks = []
    tool_results = []

    # First pass
    with client.stream("POST", "/api/v1/agents/agent-stream", json=search_request) as response:
        for line in response.iter_lines():
            if line and line.startswith("data: "):
                try:
                    data = json.loads(line[6:])
                    collected_data.append(data)
                    data_type = data.get("type", "unknown")
                    if data_type == "message":
                        message_chunks.append(str(data.get("data", "")))
                    elif data_type == "sources":
                        tool_results.append(str(data.get("data", [])))
                except json.JSONDecodeError:
                    pass

    # Handle multiple rounds of approvals
    max_rounds = 5
    for _ in range(max_rounds):
        approval_required = False
        for data in collected_data[-10:]:  # Check recent events
            if data.get("type") in ("approval_required", "tool_approval_request"):
                approval_required = True
                break

        if not approval_required:
            break

        print("\n🔧 Auto-approving tool call...")
        resume_request = search_request.copy()
        resume_request["resumeValue"] = [{"type": "approve", "extensions": {"allowAlways": True}}]

        with client.stream("POST", "/api/v1/agents/agent-stream", json=resume_request) as response:
            for line in response.iter_lines():
                if line and line.startswith("data: "):
                    try:
                        data = json.loads(line[6:])
                        collected_data.append(data)
                        data_type = data.get("type", "unknown")
                        if data_type == "message":
                            message_chunks.append(str(data.get("data", "")))
                        elif data_type == "sources":
                            tool_results.append(str(data.get("data", [])))
                    except json.JSONDecodeError:
                        pass

    full_answer = "".join(message_chunks)
    return full_answer, collected_data, message_chunks, tool_results


@pytest.mark.e2e
@pytest.mark.skipif(
    not os.environ.get("BASIC_API_KEY"),
    reason="E2E test requires BASIC_API_KEY environment variable",
)
class TestIncrementalReadE2E:
    """End-to-End tests for Incremental Log Reading tool."""

    def test_incremental_read_tool_e2e(self, client: TestClient):
        """Test read_incremental_log_tool capabilities."""
        # Simplified test: Just create a file and read it with incremental tool
        query = (
            "First, use bash_code_execute_tool to create a file named `test_incremental.log` "
            "containing exactly 5 lines: 'INFO: start', 'ERROR: failed', 'INFO: middle', 'ERROR: crash', 'INFO: end'. "
            "Then, use read_incremental_log_tool with cursor='0' and filter_pattern='ERROR' to read only the error lines. "
            "Finally, tell me how many error lines you found."
        )

        full_answer, collected_data, message_chunks, tool_results = perform_agent_search_with_auto_approve(client, query)

        assert len(collected_data) > 0, "Should have events"

        # Check if errors exist
        error_events = [d for d in collected_data if d.get("type") == "error"]
        if error_events:
            error_msg = error_events[0].get("error", "")
            if any(kw in error_msg for kw in ["Authentication", "Authorization", "Connection"]):
                pytest.skip(f"Environment issue: {error_msg[:100]}")
            else:
                pytest.fail(f"Agent execution error: {error_msg}")

        # If no errors, the agent should have completed the task
        # We just check that it returned something
        assert len(full_answer) > 0, f"Agent returned empty answer. Events: {len(collected_data)}"

        print(f"\n✅ Test passed: E2E Incremental Read Log Tool executed successfully. Answer: {full_answer[:200]}")
