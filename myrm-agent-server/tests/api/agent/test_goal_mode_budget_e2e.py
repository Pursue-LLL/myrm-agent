"""端到端集成测试：Goal 模式预算预警与熔断机制

测试场景：
1. test_goal_mode_message_with_budget: 验证 Goal 模式消息流式响应
2. test_budget_warning_threshold: 验证预算预警机制
3. test_budget_limit_exceeded: 验证预算耗尽熔断
"""

import json
import os
import uuid
from typing import Optional

import pytest
from fastapi.testclient import TestClient

from tests.api.agent.utils import get_model_selection


def perform_agent_stream(
    client: TestClient,
    query: str,
    chat_id: str,
    goal_budget: Optional[dict[str, object]] = None,
) -> tuple[str, list[dict[str, object]], dict[str, object] | None]:
    """执行 Agent 搜索并收集响应"""
    request_data: dict[str, object] = {
        "messageId": str(uuid.uuid4()),
        "chatId": chat_id,
        "query": query,
        "modelSelection": get_model_selection(),
        "actionMode": "agent",
    }
    if goal_budget:
        request_data["goal"] = goal_budget

    collected_data = []
    message_chunks = []
    goal_status = None

    with client.stream(
        "POST", "/api/v1/agents/agent-stream", json=request_data
    ) as response:
        assert response.status_code == 200
        for line in response.iter_lines():
            if line and line.startswith("data: "):
                try:
                    data = json.loads(line[6:])
                    collected_data.append(data)
                    event_type = data.get("type", "unknown")

                    if event_type == "message":
                        content = data.get("data", "")
                        if content:
                            message_chunks.append(str(content))
                    elif event_type == "message_end":
                        if "goal_status" in data:
                            goal_status = data["goal_status"]
                    elif event_type == "goal_status":
                        goal_status = data.get("data")
                except json.JSONDecodeError:
                    pass

    return "".join(message_chunks), collected_data, goal_status


@pytest.mark.e2e
@pytest.mark.skipif(
    not os.environ.get("BASIC_API_KEY"),
    reason="E2E test requires BASIC_API_KEY environment variable",
)
class TestGoalModeBudgetE2E:
    """真实链路测试 Goal 模式预算熔断与恢复"""

    def test_e2e_goal_budget_exhaustion_and_resume(self, client: TestClient):
        chat_id = f"test-goal-e2e-{uuid.uuid4().hex[:8]}"

        # 1. 发送消息，设定一个极小的预算 (e.g., 5 tokens)，预期必然会耗尽
        budget = {"maxTokens": 5}
        query = "Hello, please reply with a long sentence."

        answer, events, goal_status = perform_agent_stream(
            client, query, chat_id, goal_budget=budget
        )

        # 验证是否返回了 goal_status
        assert goal_status is not None, "message_end should contain goal_status"

        # 验证状态是否变成了 budget_limited
        assert (
            goal_status["status"] == "budget_limited"
        ), "Goal should be budget_limited after exhausting 5 tokens"
        assert (
            goal_status["tokens_used"] >= 5
        ), "Tokens used should be at least the budget"

        goal_status["goal_id"]

        # 验证系统级通知消息 (The backend sends a warning message when budget is limited)
        warning_msg = "\n\n**预算已耗尽，任务自动暂停。**"
        has_warning = any(
            d.get("type") == "message" and d.get("data") == warning_msg for d in events
        )
        assert (
            has_warning
        ), "Should yield a budget limited warning message to the chat stream"

        # 2. 追加预算
        add_budget_response = client.post(
            f"/api/v1/goals/{chat_id}/budget", json={"additional_tokens": 100000}
        )
        if add_budget_response.status_code != 200:
            print("ERROR response:", add_budget_response.json())
        assert add_budget_response.status_code == 200
        budget_data = add_budget_response.json()
        assert budget_data["status"] == "success"
        assert budget_data["new_budget"]["max_tokens"] >= 100005

        # 3. 恢复状态
        resume_response = client.post(
            f"/api/v1/goals/{chat_id}/status", json={"action": "resume"}
        )
        assert resume_response.status_code == 200
        resume_data = resume_response.json()
        assert resume_data["status"] == "success"
        assert resume_data["new_status"] == "active"

        # 4. 再次发送消息，验证能够正常继续并且 budget_status 是 active
        query2 = "Are you still there?"
        answer2, events2, goal_status2 = perform_agent_stream(client, query2, chat_id)

        assert goal_status2 is not None
        assert goal_status2["status"] in [
            "active",
            "paused",
        ], "Goal should not be budget_limited anymore"
        assert (
            goal_status2["tokens_used"] > goal_status["tokens_used"]
        ), "Tokens used should have increased"
        assert goal_status2["budget"]["max_tokens"] >= 100005

    def test_goal_mode_without_max_tokens_does_not_crash(self, client: TestClient):
        """Goal budget omitting maxTokens should not crash the stream."""
        chat_id = f"test-goal-no-max-{uuid.uuid4().hex[:8]}"
        budget = {"acceptance_criteria": []}
        query = "帮我深度调研排名前2的开源大语言模型，比较它们的架构和适用场景，并生成一份简短的对比报告。用中文回答。"

        answer, events, goal_status = perform_agent_stream(client, query, chat_id, goal_budget=budget)

        assert goal_status is not None, "message_end should contain goal_status"
        assert goal_status["budget"]["max_tokens"] is None
        assert goal_status["status"] in [
            "active",
            "paused",
            "complete",
            "needs_human_review",
        ], f"Unexpected goal status: {goal_status['status']}"
        assert isinstance(answer, str)
