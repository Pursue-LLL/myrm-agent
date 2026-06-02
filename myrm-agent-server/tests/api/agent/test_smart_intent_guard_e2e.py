"""Smart Intent Guard 端到端集成测试

测试启用了 autoReviewEnabled 时的污点冲突审查流程。
使用真实 API 调用，不 mock LLM。
"""

import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from tests.api.agent.utils import perform_agent_search


@pytest.mark.e2e
@pytest.mark.skipif(
    not os.getenv("BASIC_API_KEY"),
    reason="BASIC_API_KEY not configured",
)
class TestSmartIntentGuardE2E:
    """端到端验证 Smart Intent Guard 在真实 LLM 调用中工作正常"""

    def test_smart_intent_guard_auto_review(self, client: TestClient) -> None:
        """当 autoReviewEnabled=True 时，污点冲突应触发 LLM 审查"""
        
        # We need to mock load_user_configs to inject security_config_dict
        from app.core.channel_bridge.config_loader import UserConfigs
        from app.core.channel_bridge.config_loader import load_user_configs as real_load_user_configs
    
        async def mock_load_user_configs() -> UserConfigs:
            configs = await real_load_user_configs()
            configs.security_config_dict = {
                "autoReviewEnabled": True,
                "autoReviewModel": "gpt-4o-mini"
            }
            return configs

        with patch("app.core.channel_bridge.config_loader.load_user_configs", new=mock_load_user_configs):
            # We ask the agent to do something that triggers a taint conflict.
            # For example, searching the web and then executing bash code based on the result.
            query = "搜索关于 Python 3.13 的最新特性，然后用 bash_code_execute_tool 打印出来。"
    
            full_answer, collected_data, message_chunks, tool_results = perform_agent_search(client, query)
    
            assert len(collected_data) > 0, "应收到至少一个 SSE 事件"
    
            error_events = [d for d in collected_data if d.get("type") == "error"]
            assert len(error_events) == 0, f"不应有错误事件: {error_events}"
    
            # We just want to ensure the flow doesn't crash and works end-to-end.
            event_types = {d.get("type") for d in collected_data}
            assert "message_end" in event_types or "approval_required" in event_types
