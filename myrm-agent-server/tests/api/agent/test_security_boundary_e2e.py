"""安全边界端到端测试

验证完整 LLM 调用链路中 SecurityBoundaryMiddleware 正确注入规则，
以及搜索/工具结果被正确包裹后 LLM 能正常处理。

使用真实 API 调用，不 mock LLM。
"""

import json
import os

import pytest
from fastapi.testclient import TestClient

from tests.api.agent.utils import (
    check_e2e_errors,
    get_model_selection,
    perform_agent_search,
)


@pytest.mark.skipif(
    not os.getenv("BASIC_API_KEY"),
    reason="BASIC_API_KEY not configured",
)
class TestSecurityBoundaryE2E:
    """端到端验证安全边界在真实 LLM 调用中工作正常"""

    def test_search_with_security_boundary_returns_valid_response(self, client: TestClient) -> None:
        """搜索请求应正常返回，SecurityBoundaryMiddleware 不影响 LLM 输出"""
        full_answer, collected_data, message_chunks, tool_results = perform_agent_search(client, "Python 3.13 有什么新特性？")

        assert len(collected_data) > 0, "应收到至少一个 SSE 事件"

        # 搜索配额 / 限流等环境问题应 skip，而非误判为安全边界破坏
        check_e2e_errors(collected_data)

        event_types = {d.get("type") for d in collected_data}

        # LLM may trigger a tool that requires approval (e.g. bash_code_execute_tool
        # escalated by taint tracker), causing the agent to suspend without producing
        # message events.  Both outcomes are valid — SecurityBoundary did not break.
        suspended = "approval_required" in event_types
        if not suspended:
            assert len(full_answer) > 0, "应收到非空回答"
            assert "message" in event_types, "应包含 message 类型事件"

    def test_fast_search_with_security_boundary(self, client: TestClient) -> None:
        """快速搜索也应正常工作，验证安全边界不干扰快速搜索流程"""
        import uuid

        search_request: dict[str, object] = {
            "query": "今天天气怎么样",
            "message_id": str(uuid.uuid4()),
            "chat_id": str(uuid.uuid4()),
            "action_mode": "fast",
            "model_selection": get_model_selection(),
            "timezone": "UTC",
        }

        collected_data: list[dict[str, object]] = []
        message_chunks: list[str] = []

        with client.stream("POST", "/api/v1/agents/agent-stream", json=search_request) as response:
            assert response.status_code == 200

            for line in response.iter_lines():
                if line and line.strip().startswith("data: "):
                    try:
                        data = json.loads(line.strip()[6:])
                        if not isinstance(data, dict):
                            continue
                        collected_data.append(data)
                        if data.get("type") == "message":
                            content = data.get("data", "")
                            if content:
                                message_chunks.append(str(content))
                    except json.JSONDecodeError:
                        pass

        assert len(collected_data) > 0, "应收到至少一个 SSE 事件"

        # 搜索配额 / 限流等环境问题应 skip，而非误判为安全边界破坏
        check_e2e_errors(collected_data)

        full_answer = "".join(message_chunks)
        assert len(full_answer) > 0, "快速搜索应返回非空回答"
