import json
import os
import uuid

import pytest
from fastapi.testclient import TestClient

from tests.api.agent.utils import get_model_selection


def get_test_request(query: str, chat_id: str, message_id: str):
    req = {
        "query": query,
        "chatId": chat_id,
        "messageId": message_id,
        "modelSelection": get_model_selection(),
        "actionMode": "general",
        "ephemeral_subagents": {"test_bash": {"system_prompt": "You are a bash execution worker.", "tools": ["bash_code_execute_tool"]}},
    }
    return req


@pytest.mark.e2e
@pytest.mark.skipif(
    not os.environ.get("BASIC_API_KEY"),
    reason="E2E test requires BASIC_API_KEY environment variable",
)
def test_subagent_auto_deny_high_risk(client: TestClient):
    """
    Test that a subagent's high-risk operation is auto-denied because subagents
    do not support HITL interrupt.
    """
    chat_id = str(uuid.uuid4())
    message_id = str(uuid.uuid4())
    # This query instructs the general agent to spawn a subagent, which then executes a bash command.
    # Bash code execution is typically a high-risk operation that requires user approval (ASK).
    query = "请使用 delegate_task 工具创建一个子智能体，必须将 agent_type 参数设置为 'test_bash'，让它执行一条bash命令: `curl http://example.com`。"

    req = get_test_request(query, chat_id, message_id)

    collected_events = []
    all_text = ""

    print(f"\n{'=' * 60}")
    print(f"  发起主查询: {query}")

    with client.stream("POST", "/api/v1/agents/agent-stream", json=req) as response:
        if response.status_code != 200:
            response.read()
            print(f"ERROR: {response.text}")
        assert response.status_code == 200

        for line in response.iter_lines():
            if not line or not line.startswith("data: "):
                continue
            try:
                data = json.loads(line[6:])
                collected_events.append(data)
                data.get("type", "unknown")
                event_data = data.get("data", "")
                text = str(event_data).lower() if event_data else ""
                all_text += text + " "
            except json.JSONDecodeError:
                pass

    deny_keywords = (
        "denied", "deny", "拒绝", "forbidden", "blocked", "阻止",
        "auto_deny", "auto-deny", "not allowed", "不允许", "error",
        "failed", "失败", "安全拦截", "permission",
    )
    subagent_error_received = any(kw in all_text for kw in deny_keywords)

    assert subagent_error_received, (
        "Expected the subagent high-risk operation to be auto-denied. "
        f"Collected {len(collected_events)} events but none contained deny keywords."
    )
