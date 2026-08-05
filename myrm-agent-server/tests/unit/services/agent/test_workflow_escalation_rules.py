"""Unit tests for workflow_escalation.py — rule-based DW Engine suggestion detector."""

from __future__ import annotations

from app.services.agent.stream_session.workflow_escalation import (
    _extract_text,
    should_suggest_workflow,
)


class TestShouldSuggestWorkflow:
    """Tests for the pure detection function."""

    def test_non_reasoning_tier_returns_false(self) -> None:
        query = "1. 调研 2. 分析 3. 总结 4. 对比 5. 汇报"
        assert should_suggest_workflow(query, routing_tier="standard") is False
        assert should_suggest_workflow(query, routing_tier="simple") is False
        assert should_suggest_workflow(query, routing_tier=None) is False

    def test_short_query_returns_false(self) -> None:
        assert should_suggest_workflow("短查询", routing_tier="reasoning") is False
        assert should_suggest_workflow("", routing_tier="reasoning") is False

    def test_numbered_list_triggers(self) -> None:
        query = "帮我分别调研以下5家竞品的定价策略：\n1. Claude\n2. ChatGPT\n3. Gemini\n4. Perplexity\n5. Copilot"
        assert should_suggest_workflow(query, routing_tier="reasoning") is True

    def test_circled_numbers_with_parallel_keyword_triggers(self) -> None:
        query = "请分别完成以下任务：①调研竞品定价 ②分析市场份额 ③对比核心功能 ④总结优劣势"
        assert should_suggest_workflow(query, routing_tier="reasoning") is True

    def test_circled_numbers_alone_conservative(self) -> None:
        query = "请完成以下任务：①调研竞品定价 ②分析市场份额 ③对比核心功能 ④总结优劣势"
        # Single pattern category alone doesn't reach threshold (score=3 < 4)
        assert should_suggest_workflow(query, routing_tier="reasoning") is False

    def test_parallel_keywords_with_quantity(self) -> None:
        query = "对比分析这3家公司的市场表现、盈利能力和增长潜力，每家都要独立深入分析"
        assert should_suggest_workflow(query, routing_tier="reasoning") is True

    def test_english_sequential_with_numbered_list(self) -> None:
        query = "Compare these 3 products:\n1. Redis performance and pricing\n2. Memcached scalability\n3. DragonflyDB features\nFirst analyze each, then compare them side by side"
        assert should_suggest_workflow(query, routing_tier="reasoning") is True

    def test_english_sequential_alone_conservative(self) -> None:
        query = "First research the pricing of 3 competitors, then analyze their features, next compare user reviews, and finally summarize the findings"
        # Sequential keywords alone without numbered structure don't reach threshold
        assert should_suggest_workflow(query, routing_tier="reasoning") is False

    def test_simple_reasoning_query_does_not_trigger(self) -> None:
        query = "帮我写一篇关于人工智能发展趋势的深度分析文章，要求有数据支撑"
        assert should_suggest_workflow(query, routing_tier="reasoning") is False

    def test_single_numbered_item_does_not_trigger(self) -> None:
        query = "我有3年的Python开发经验，帮我写一份简历"
        assert should_suggest_workflow(query, routing_tier="reasoning") is False

    def test_multimodal_list_input(self) -> None:
        query = [
            {"type": "text", "text": "帮我分别调研以下5家公司：\n1. Apple\n2. Google\n3. Microsoft\n4. Amazon\n5. Meta"},
        ]
        assert should_suggest_workflow(query, routing_tier="reasoning") is True

    def test_multimodal_image_only_returns_false(self) -> None:
        query = [{"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}}]
        assert should_suggest_workflow(query, routing_tier="reasoning") is False

    def test_chinese_parallel_markers(self) -> None:
        query = "分别调研美国、日本、欧洲的AI监管政策，各自的特点和对企业的影响，并行分析后给出总结"
        assert should_suggest_workflow(query, routing_tier="reasoning") is True


class TestExtractText:
    """Tests for the multimodal text extraction helper."""

    def test_string_passthrough(self) -> None:
        assert _extract_text("hello world") == "hello world"

    def test_list_extraction(self) -> None:
        content = [
            {"type": "text", "text": "first"},
            {"type": "image_url", "image_url": {"url": "..."}},
            {"type": "text", "text": "second"},
        ]
        assert _extract_text(content) == "first second"

    def test_empty_list(self) -> None:
        assert _extract_text([]) == ""

    def test_non_dict_items_ignored(self) -> None:
        assert _extract_text(["not_a_dict", 123]) == ""  # type: ignore[list-item]
