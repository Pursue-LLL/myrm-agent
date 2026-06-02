"""Auto Restore Domains E2E Test

测试 /api/v1/agents/agent-stream 端点是否正确处理 auto_restore_domains 参数。
"""

import json
import logging
import os

import pytest
from fastapi.testclient import TestClient

from tests.api.agent.utils import get_model_selection


@pytest.mark.e2e
@pytest.mark.skipif(
    not os.environ.get("BASIC_API_KEY"),
    reason="E2E test requires BASIC_API_KEY environment variable",
)
class TestAutoRestoreDomains:
    """自动恢复登录态测试"""

    def test_auto_restore_domains_logging(self, client: TestClient, caplog):
        """测试 Agent 启动时是否正确触发了 auto_restore_domains 的日志"""
        query = "请告诉我今天的天气。"

        # Uses BASIC_MODEL / BASIC_BASE_URL / BASIC_API_KEY from environment (.env).
        model_selection = get_model_selection()

        test_domains = ["test-domain-1.com", "test-domain-2.org"]

        request_data = {
            "messageId": "test_msg_auto_restore",
            "query": query,
            "modelSelection": model_selection,
            "agentConfig": {
                "skillIds": [],
                "enabledBuiltinTools": ["web_search", "browser"],
                "autoRestoreDomains": test_domains
            }
        }

        # 捕获 INFO 级别的日志
        with caplog.at_level(logging.INFO):
            response = client.post(
                "/api/v1/agents/agent-stream",
                json=request_data,
                headers={"Accept": "text/event-stream"},
            )

            # 读取流式响应直到结束，确保 Agent 初始化完成
            for line in response.iter_lines():
                if line:
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str == "[DONE]":
                            break
                        try:
                            data = json.loads(data_str)
                            # 忽略认证错误，因为我们只是为了测试日志
                            if data.get("type") == "error":
                                error_msg = data.get("error", "")
                                if "AuthenticationError" not in error_msg and "Invalid API Key" not in error_msg:
                                    pytest.fail(f"Agent stream error: {data}")
                        except json.JSONDecodeError:
                            pass

        # 验证日志中是否包含了自动恢复的提示
        log_found = False
        for record in caplog.records:
            if "BrowserSession created: context_key=" in record.message:
                log_found = True
                break
        
        assert log_found, "The BrowserSession creation log was not found."
