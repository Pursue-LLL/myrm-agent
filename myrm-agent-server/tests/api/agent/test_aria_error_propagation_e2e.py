"""Aria Error Propagation E2E Test

测试 /api/v1/agents/agent-stream 端点，确保在浏览器快照提取失败时（如 selector 不存在），
底层抛出的 AriaAcquisitionError 能够正确转化为诊断信息并被大模型捕获和理解。
"""

import json
import os

import pytest
from fastapi.testclient import TestClient

from tests.api.agent.utils import get_model_selection


@pytest.mark.e2e
@pytest.mark.skipif(
    not os.environ.get("BASIC_API_KEY"),
    reason="E2E test requires BASIC_API_KEY environment variable",
)
class TestAriaErrorPropagation:
    """ARIA 错误传播机制测试"""

    def test_aria_error_recovery(self, client: TestClient):
        """测试 Agent 遇到不存在的 selector 时是否能收到正确的错误并在回复中反映出来"""
        # 指示 Agent 去抓取一个不存在的元素，观察它是否能捕获到底层抛出的 RefNotFoundError 或 AriaAcquisitionError
        query = "请访问 https://example.com/ 并尝试使用 browser_snapshot 工具提取选择器为 '#this_does_not_exist_at_all_123' 的元素的 DOM/ARIA 树。由于该元素必定不存在，底层提取必定失败并抛出带有诊断建议的系统错误。请仔细阅读你收到的工具调用报错，并原文复述你收到了什么报错信息（特别是关于 Recovery Suggestions 的内容）。"

        model_selection = get_model_selection()
        if model_selection and "model" in model_selection:
            model_name = str(model_selection["model"])
            if not model_name.startswith("openai/"):
                model_selection["model"] = f"openai/{model_name}"
            model_selection["providerId"] = "openai"

        request_data = {
            "messageId": "test_aria_err_123",
            "query": query,
            "modelSelection": model_selection,
            "userInstructions": "请必须执行 browser_snapshot 工具调用，并在最后总结你收到的错误信息。",
            "agentConfig": {
                "skillIds": [],
                "enabledBuiltinTools": ["web_search", "browser"],
            },
        }

        collected_data = []
        tool_calls = []
        error_msg = None

        with client.stream("POST", "/api/v1/agents/agent-stream", json=request_data) as response:
            if response.status_code != 200:
                response.read()
                print(f"Error: {response.text}")
            assert response.status_code == 200

            for line in response.iter_lines():
                if not line or not line.startswith("data: "):
                    continue
                try:
                    data = json.loads(line[6:])
                    collected_data.append(data)
                    event_type = data.get("type")

                    if event_type == "tasks_steps":
                        tool_name = data.get("tool_name")
                        if tool_name:
                            tool_calls.append(tool_name)
                            print(f"🔧 工具调用: {tool_name}")
                    elif event_type == "error":
                        error_msg = data.get("error", "")
                        print(f"❌ 错误: {error_msg}")
                except json.JSONDecodeError:
                    pass

        has_browser_tools = any(tool.startswith("browser_") for tool in tool_calls)

        if error_msg:
            # 忽略环境或网络错误
            if any(
                kw in error_msg
                for kw in [
                    "Timeout",
                    "timeout",
                    "Connection",
                    "Authentication",
                    "litellm",
                ]
            ):
                pytest.skip(f"环境或网络错误: {error_msg}")
            else:
                pytest.fail(f"Agent 执行出错: {error_msg}")

        assert has_browser_tools, "Agent 应该调用了浏览器相关工具"

        # 收集最终回复
        final_answer = "".join([d.get("data", "") for d in collected_data if d.get("type") == "message"])
        print(f"\n💬 最终回答: {final_answer}")

        # 验证 LLM 确实收到了带有建议的底层错误
        assert (
            "this_does_not_exist_at_all_123" in final_answer
            or "AriaAcquisitionError" in final_answer
            or "Recovery Suggestion" in final_answer
            or "not found" in final_answer.lower()
            or "Failed to acquire ARIA tree" in final_answer
        ), "LLM 未能在回答中报告捕获到的准确诊断信息"

        print("\n✅ ARIA 错误传播机制 E2E 测试通过！")
