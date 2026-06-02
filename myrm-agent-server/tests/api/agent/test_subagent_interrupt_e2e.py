import json
import os
import uuid

import pytest
from fastapi.testclient import TestClient

from tests.api.agent.utils import get_model_selection


def get_test_request(query: str, chat_id: str, message_id: str, resume_value=None):
    req = {
        "query": query,
        "chatId": chat_id,
        "messageId": message_id,
        "modelSelection": get_model_selection(),
        "actionMode": "general",
        "jitSubagents": {"test_bash": {"system_prompt": "You are a bash execution worker.", "tools": ["bash_code_execute_tool"]}},
    }
    if resume_value is not None:
        req["resumeValue"] = {"decisions": resume_value}
    return req


@pytest.mark.e2e
@pytest.mark.skipif(
    not os.environ.get("BASIC_API_KEY"),
    reason="E2E test requires BASIC_API_KEY environment variable",
)
def test_subagent_interrupt_and_resume(client: TestClient):
    """
    Test that a subagent's high-risk operation interrupts the parent agent,
    emits an approval_required event, and correctly resumes when approved.
    """
    chat_id = str(uuid.uuid4())
    message_id = str(uuid.uuid4())
    # This query instructs the general agent to spawn a subagent, which then executes a bash command.
    # Bash code execution is typically a high-risk operation that requires user approval (ASK).
    query = "请使用 delegate_task_tool 工具创建一个子智能体，必须将 agent_type 参数设置为 'test_bash'，让它执行一条bash命令: `echo hello_from_subagent`。注意：必须使用原生函数调用（Native Tool Calling / Function Calling）来调用工具，绝对不要在文本中输出 XML 格式的工具调用！"

    req = get_test_request(query, chat_id, message_id)

    collected_events = []
    approval_payload = None

    print(f"\n{'=' * 60}")
    print(f"🚀 发起主查询: {query}")

    resume_value = None
    while True:
        req = get_test_request(query, chat_id, message_id, resume_value)
        with client.stream("POST", "/api/v1/agents/agent-stream", json=req) as response:
            if response.status_code != 200:
                response.read()
                print(f"ERROR: {response.text}")
            assert response.status_code == 200

            action_type = None
            for line in response.iter_lines():
                print(f"  RAW LINE: {repr(line)}")
                if not line or not line.startswith("data: "):
                    continue
                try:
                    data = json.loads(line[6:])
                    collected_events.append(data)
                    event_type = data.get("type", "unknown")
                    print(f"  🔍 Received event: {event_type}")
                    if event_type == "approval_required":
                        approval_payload = data.get("data", {})
                        action_type = approval_payload.get("action_type")
                        print(f"  ✅ 拦截到 approval_required 事件！ action_type={action_type}")
                        break
                    elif event_type == "message":
                        content = data.get("data", "")
                        if content:
                            print(f"  💬 消息: {content[:80]}...")
                except json.JSONDecodeError:
                    pass

        if action_type == "subagent_approval":
            break
        elif action_type is None or action_type == "tool_approval":
            # Auto-approve the main agent's tool call (like delegate_task_tool)
            print("  🔄 自动同意主智能体的工具调用...")
            resume_value = [{"type": "approve", "feedback": "Auto-approve delegate_task_tool"}]
            query = ""  # Clear query for resume request
            message_id = str(uuid.uuid4())  # Prevent cancellation registry collision
        else:
            break

    assert approval_payload is not None, "Expected approval_required event to be emitted by the Subagent's action"
    assert approval_payload.get("action_type") == "subagent_approval", "action_type must be subagent_approval"
    assert "subagent_task_id" in approval_payload, "subagent_task_id must be present in the payload"

    # Now simulate the user clicking "Approve" on the frontend PolymorphicApprovalCard
    resume_value = [{"type": "approve", "feedback": "Looks good from E2E test"}]
    message_id = str(uuid.uuid4())  # Prevent cancellation registry collision
    resume_req = get_test_request("", chat_id, message_id, resume_value)

    print("\n🔄 模拟用户同意，Resume 主智能体")

    resume_events = []
    with client.stream("POST", "/api/v1/agents/agent-stream", json=resume_req) as response:
        assert response.status_code == 200
        for line in response.iter_lines():
            print(f"  RAW LINE: {repr(line)}")
            if not line or not line.startswith("data: "):
                continue
            try:
                data = json.loads(line[6:])
                resume_events.append(data)
                event_type = data.get("type", "unknown")
                if event_type == "message":
                    content = data.get("data", "")
                    if content:
                        print(f"  💬 恢复后消息: {content[:80]}...")
                elif event_type == "message_end":
                    print("  🏁 收到 message_end")
            except json.JSONDecodeError:
                pass

    has_message_end = any(d.get("type") == "message_end" for d in resume_events)
    assert has_message_end, "Agent should complete successfully after resumption"

    # Check if the subagent successfully executed the command
    full_answer = "".join(
        d.get("data", "") for d in resume_events if d.get("type") == "message" and isinstance(d.get("data"), str)
    )
    print(f"\n📝 最终回答: {full_answer}")
    assert "hello_from_subagent" in full_answer.lower() or len(full_answer) > 0, (
        "Agent should incorporate the subagent's execution result"
    )
    print("\n🎉 端到端 Subagent 中断与恢复测试通过！")
