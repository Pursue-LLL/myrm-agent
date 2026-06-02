"""React SPA & DOM Enhancer E2E Test

测试 /api/v1/agents/general-stream 端点对 SPA 页面和 React 事件的感知能力。
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
class TestReactSPAAgent:
    """React SPA 交互测试"""

    def test_react_spa_interaction(self, client: TestClient):
        """测试 Agent 在 React SPA 页面上的交互能力"""
        # 我们让 Agent 访问一个简单的 React SPA 示例页面，例如 TodoMVC React
        query = "请访问 https://demo.playwright.dev/todomvc/#/ ，这是一个 React 写的 Todo 应用。请在输入框中输入 'Test SPA Interaction' 并回车添加待办事项。然后点击刚添加的待办事项前面的复选框（Toggle）将其标记为完成。请务必使用浏览器工具完成这些操作。"

        model_selection = get_model_selection()
        if model_selection and "model" in model_selection:
            model_name = str(model_selection["model"])
            if not model_name.startswith("openai/"):
                model_selection["model"] = f"openai/{model_name}"
            model_selection["providerId"] = "openai"

        request_data = {
            "messageId": "test_msg_123",
            "query": query,
            "modelSelection": model_selection,
            "userInstructions": "请严格按照要求使用浏览器工具。不要只回答，必须执行动作。",
            "agentConfig": {
                "skillIds": [],
                "enabledBuiltinTools": ["web_search", "browser"]
            }
        }

        collected_data = []
        tool_calls = []
        error_msg = None

        with client.stream(
            "POST", "/api/v1/agents/agent-stream", json=request_data
        ) as response:
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

        # 验证是否调用了浏览器工具
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

        assert has_browser_tools, "Agent 应该调用了浏览器工具"
        print("\n✅ React SPA E2E 测试通过！")
