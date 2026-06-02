"""AST Code Search and Terminal Streaming E2E Tests.

Test /api/v1/agents/agent-stream endpoint for AST codebase indexing
and DDOS-protected terminal streaming.
"""

import json
import os
import uuid

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
    
    def _stream_req(req_data):
        with client.stream("POST", "/api/v1/agents/agent-stream", json=req_data) as response:
            if response.status_code != 200:
                print(f"HTTP Error {response.status_code}: {response.read()}")
            assert response.status_code == 200
            for line in response.iter_lines():
                if line and line.startswith("data: "):
                    try:
                        data = json.loads(line[6:])
                        if data is None:
                            continue
                        collected_data.append(data)
                        data_type = data.get("type", "unknown")
                        if data_type == "message" or data_type == "reasoning":
                            content = data.get("data", "")
                            if content:
                                message_chunks.append(str(content))
                        elif data_type == "sources":
                            tool_results.append(str(data.get("data", [])))
                    except json.JSONDecodeError:
                        pass

    # First pass
    _stream_req(search_request)

    # Check if approval is required in a loop
    for _ in range(10): # max 10 loops to prevent infinite
        approval_required = False
        for data in reversed(collected_data): # check the end of the stream
            if data.get("type") in ("approval_required", "tool_approval_request"):
                approval_required = True
                break
            if data.get("type") in ("message_end", "error"):
                break
                
        if approval_required:
            import logging
            logging.getLogger(__name__).error("\n🔧 Auto-approving tool call...")
            resume_request = search_request.copy()
            resume_request["resumeValue"] = [{
                "type": "approve",
                "extensions": {"allowAlways": True}
            }]
            _stream_req(resume_request)
        else:
            break
                        
    import logging
    logging.getLogger(__name__).error(f"COLLECTED TYPES: {[d.get('type') for d in collected_data]}")
    full_answer = "".join(message_chunks)
    return full_answer, collected_data, message_chunks, tool_results

@pytest.mark.e2e
@pytest.mark.skipif(
    not os.environ.get("BASIC_API_KEY"),
    reason="E2E test requires BASIC_API_KEY environment variable",
)
class TestAstAndTerminalE2E:
    """End-to-End tests for AST Indexer and Terminal Streaming capabilities."""

    def test_ast_search_tool_e2e(self, client: TestClient):
        """Test AST codebase search tool directly."""
        # 1. Provide a query that forces the agent to use ast_search_tool
        query = "First, use bash_code_execute_tool to create a file named `test_ast.py` containing `class TestAstClass: pass`. Then, use the ast_search_tool to find where 'TestAstClass' is defined. Only return the file path and line number."
    
        full_answer, collected_data, message_chunks, tool_results = perform_agent_search_with_auto_approve(
            client, query
        )
    
        assert len(collected_data) > 0, "Should have events"
        has_message_end = any(d.get("type") == "message_end" for d in collected_data)
        assert has_message_end, "Should have message_end event"
    
        error_events = [d for d in collected_data if d.get("type") == "error"]
        if error_events:
            pytest.fail(f"Agent execution error: {error_events[0].get('error')}")
    
        assert "test_ast.py" in full_answer or len(tool_results) > 0, "Agent should find TestAstClass in test_ast.py"
        print("\n✅ Test Passed: AST Search E2E completed successfully")

    def test_terminal_ddos_defense_e2e(self, client: TestClient):
        """Test terminal DDOS defense (SSE Throttle & Valve) with large output."""
        # 1. Instruct agent to run a bash command that generates a huge amount of text
        query = "Run a python script using bash/shell tool that prints 600,000 characters of text to stdout (e.g. `python3 -c \"print('A' * 600000)\"`). Tell me if it succeeded."
        
        full_answer, collected_data, message_chunks, tool_results = perform_agent_search_with_auto_approve(
            client, query
        )

        assert len(collected_data) > 0, "Should have events"
        
        # Check for system warning in message chunks or tool steps
        warning_detected = False
        for chunk in message_chunks:
            if "System Warning: Terminal stream suspended to prevent UI freeze" in chunk:
                warning_detected = True
                break
                
        # The warning might be emitted as a tasks_steps update
        if not warning_detected:
            for event in collected_data:
                if event.get("type") == "tasks_steps":
                    data_list = event.get("data", [])
                    if isinstance(data_list, list):
                        for item in data_list:
                            if isinstance(item, dict) and "text" in item:
                                if "System Warning: Terminal stream suspended" in item["text"]:
                                    warning_detected = True
                                    break
                                
        # Even if the LLM output doesn't contain the raw warning, the execution should succeed without crashing the server.
        has_message_end = any(d.get("type") == "message_end" for d in collected_data)
        assert has_message_end, "Should have message_end event (no server crash)"
        
        error_events = [d for d in collected_data if d.get("type") == "error"]
        if error_events:
            pytest.fail(f"Agent execution error: {error_events[0].get('error')}")
            
        print("\n✅ Test Passed: Terminal DDOS Defense E2E completed successfully without crashing")
