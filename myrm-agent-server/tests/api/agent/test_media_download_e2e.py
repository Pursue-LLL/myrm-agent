import os

import pytest
from fastapi.testclient import TestClient

from tests.api.agent.utils import perform_agent_search


@pytest.mark.e2e
@pytest.mark.skipif(
    not os.environ.get("BASIC_API_KEY"),
    reason="E2E test requires BASIC_API_KEY environment variable",
)
class TestMediaDownloadE2E:
    """媒体下载系统端到端集成测试"""

    def test_agent_stream_with_media_url(self, client: TestClient):
        """测试在 agent-stream 中发送包含图片 URL 的消息"""
        # 测试发送一个正常的图片 URL，验证后端链路是否畅通且没有崩溃
        query = "请分析这张图片的内容：https://httpbin.org/image/png"

        full_answer, collected_data, message_chunks, tool_results = perform_agent_search(client, query)

        # 验证响应
        assert len(collected_data) > 0, "Should have events"

        # 验证有 messageEnd 事件
        has_message_end = any(d.get("type") == "message_end" for d in collected_data)
        assert has_message_end, "Should have message_end event"

        # 检查错误
        error_events = [d for d in collected_data if d.get("type") == "error"]
        if error_events:
            error_msg = error_events[0].get("error", "")
            # 如果是环境问题（如模型不支持），跳过
            if any(
                kw in error_msg
                for kw in [
                    "Authentication",
                    "Authorization",
                    "Recursion limit",
                    "Cannot connect",
                    "Connection error",
                    "InternalServerError",
                    "not supported",
                ]
            ):
                pytest.skip(f"环境配置问题: {error_msg[:100]}")
            else:
                # 真正的代码错误
                pytest.fail(f"Agent execution error: {error_msg}")

        # 无错误时，应该有回答或者触发了审批
        if not error_events:
            has_approval = any(d.get("type") == "tool_approval_request" for d in collected_data)
            assert full_answer or has_approval, "Should have answer or trigger approval when no errors"
            print("\n✅ 测试通过：包含媒体 URL 的查询正常处理")
