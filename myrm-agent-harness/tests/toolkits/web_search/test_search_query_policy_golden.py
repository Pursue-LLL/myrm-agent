"""Regression gate: preserve compact web_search query guardrails."""

from __future__ import annotations

from myrm_agent_harness.agent.streaming.agent_core_rules import AGENT_CORE_RULES
from myrm_agent_harness.toolkits.web_search.engine import SearchServiceConfig
from myrm_agent_harness.toolkits.web_search.web_search_agent_tools import (
    create_web_search_tool,
)

class TestWebSearchDescriptionBaseline:
    def test_tool_description_retains_compact_rewrite_rules(self) -> None:
        tool = create_web_search_tool(
            search_service_cfg=SearchServiceConfig(search_service="tavily", api_key="test-key"),
            description_locale="zh-CN",
        )
        description = tool.description or ""
        assert "Query 改写规则" in description
        assert "每条 query 脱离会话和其他 query 后都必须可理解" in description
        assert "复杂问题可额外加入一条综合 query" in description

    def test_rewrite_rules_not_in_agent_core_rules(self) -> None:
        assert "Query Rewriting Rules" not in AGENT_CORE_RULES
        assert "<rewrite_rules>" not in AGENT_CORE_RULES
