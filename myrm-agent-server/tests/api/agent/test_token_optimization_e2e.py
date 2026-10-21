"""Token 消耗优化特性端到端测试

测试以下特性：
1. Smart Differentiated Tool Output Truncation (Bash/File)
2. 确保 `agent_status` 事件正确推送 `tool_truncated` 状态
"""

import json
import os
import uuid

import pytest
from fastapi.testclient import TestClient

from tests.api.agent.utils import get_model_selection


@pytest.mark.e2e
@pytest.mark.skipif(
    not os.environ.get("BASIC_API_KEY"),
    reason="E2E test requires BASIC_API_KEY environment variable",
)
@pytest.mark.asyncio
async def test_smart_tool_truncation_file(client: TestClient) -> None:
    """测试 File 工具大输出截断及 SSE 事件推送"""
    chat_id = f"trunc-chat-{uuid.uuid4().hex[:8]}"

    # Create a large file in the agent's workspace
    data_dir = os.environ.get("MYRM_DATA_DIR", os.path.join(os.path.expanduser("~"), ".myrm"))
    workspace_dir = os.path.join(data_dir, "workspaces", f"chat_{chat_id}")
    os.makedirs(workspace_dir, exist_ok=True)
    large_file_path = os.path.join(workspace_dir, "large_file_for_test.txt")
    with open(large_file_path, "w") as f:
        f.write("A" * 15000)

    request_data = {
        "messageId": str(uuid.uuid4()),
        "query": "Please use file_read_tool to read the file large_file_for_test.txt. Do not do anything else.",
        "chatId": chat_id,
        "modelSelection": get_model_selection(),
        "actionMode": "agent",
    }

    tool_truncated_event_received = False
    truncation_metadata = None
    needs_approval = False

    with client.stream("POST", "/api/v1/agents/agent-stream", json=request_data) as response:
        assert response.status_code == 200
        print("Response status 200, iterating lines...")

        for line in response.iter_lines():
            if not line:
                continue
            print(f"LINE: {line[:50]}")

            if line.startswith("data: "):
                data_str = line[6:]
                if data_str == "[DONE]":
                    break

                try:
                    event_data = json.loads(data_str)
                    print(f"EVENT TYPE: {event_data.get('type')}")

                    # 检查 agent_status 事件
                    if event_data.get("type") == "status":
                        status_data = event_data.get("data", {})
                        if status_data.get("event") == "tool_truncated":
                            tool_truncated_event_received = True
                            truncation_metadata = status_data.get("metadata", {})
                            print(f"✅ Received tool_truncated event: {truncation_metadata}")

                    # Check if it needs approval
                    if event_data.get("type") == "approval_required":
                        needs_approval = True

                except json.JSONDecodeError:
                    continue

    if needs_approval:
        print("⚠️ Needs approval, sending resume request...")
        resume_request = {
            "messageId": str(uuid.uuid4()),
            "query": "yes",
            "chatId": chat_id,
            "resumeValue": {"decision": "approve"},
            "modelSelection": get_model_selection(),
            "actionMode": "agent",
        }

        with client.stream("POST", "/api/v1/agents/agent-stream", json=resume_request) as response:
            assert response.status_code == 200
            for line in response.iter_lines():
                if not line:
                    continue
                if line.startswith("data: "):
                    data_str = line[6:]
                    if data_str == "[DONE]":
                        break
                    try:
                        event_data = json.loads(data_str)
                        if event_data.get("type") == "status":
                            print(f"EVENT STATUS: {event_data}")
                            status_data = event_data.get("data", {})
                            if status_data.get("event") == "tool_truncated":
                                tool_truncated_event_received = True
                                truncation_metadata = status_data.get("metadata", {})
                                print(f"✅ Received tool_truncated event after approval: {truncation_metadata}")
                    except json.JSONDecodeError:
                        continue

    # 验证是否收到了截断事件
    assert tool_truncated_event_received, "Expected 'tool_truncated' event was not received."

    # 验证元数据是否包含绝对坐标
    assert truncation_metadata is not None
    assert truncation_metadata.get("type") == "file"
    assert "total_lines" in truncation_metadata
    assert "total_mb" in truncation_metadata
    assert "shown_chars" in truncation_metadata

    if os.path.exists(large_file_path):
        os.remove(large_file_path)
