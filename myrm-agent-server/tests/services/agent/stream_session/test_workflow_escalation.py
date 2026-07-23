"""Unit tests for workflow_escalation — single-agent gatekeeping (MacTalk #2).

Verifies:
1. should_suggest_workflow() pure detection on query text
2. should_suggest_workflow_for_session() session-aware guard defaults
3. Default suggest_workflow_mode = False (single-agent-by-default philosophy)
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.services.agent.stream_session.workflow_escalation import (
    should_suggest_workflow,
    should_suggest_workflow_for_session,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_session(
    query: str = "",
    routing_tier: str | None = "reasoning",
    extra_context: dict | None = None,
    engine_params: dict | None = None,
) -> MagicMock:
    session = MagicMock()
    session.request = MagicMock()
    session.request.query = query
    session.request.engine_params = engine_params
    session.routing_tier = routing_tier
    session.extra_context = extra_context if extra_context is not None else {}
    return session


SIMPLE_QUERY = "帮我写一个 Python 排序函数"

MULTI_GOAL_QUERY = (
    "请帮我完成以下任务：\n"
    "1. 调研 3 家竞品的定价策略\n"
    "2. 分别分析各家的优劣势\n"
    "3. 写一份对比报告\n"
    "4. 给出推荐方案\n"
    "5. 制作演示 PPT 大纲"
)


# ---------------------------------------------------------------------------
# should_suggest_workflow() — pure detection
# ---------------------------------------------------------------------------


class TestShouldSuggestWorkflow:
    """Pure detection function — no session state involved."""

    def test_rejects_non_reasoning_tier(self):
        assert should_suggest_workflow(MULTI_GOAL_QUERY, routing_tier="fast") is False

    def test_rejects_none_tier(self):
        assert should_suggest_workflow(MULTI_GOAL_QUERY, routing_tier=None) is False

    def test_rejects_short_query(self):
        assert should_suggest_workflow("hi", routing_tier="reasoning") is False

    def test_detects_numbered_multi_goal(self):
        assert should_suggest_workflow(MULTI_GOAL_QUERY, routing_tier="reasoning") is True

    def test_rejects_simple_reasoning_query(self):
        long_simple = "请帮我详细解释一下 Python 中的装饰器模式是如何工作的，包括它的底层原理和常见应用场景"
        assert should_suggest_workflow(long_simple, routing_tier="reasoning") is False

    def test_detects_circled_numbers_with_parallel(self):
        """Circled numbers (score=3) + parallel keyword '分别' (score=2) → triggers."""
        query = "①调研市场数据 ②分析竞品策略 ③撰写报告 ④制定方案，分别给出结论" + "x" * 10
        assert should_suggest_workflow(query, routing_tier="reasoning") is True

    def test_circled_numbers_alone_below_threshold(self):
        """Circled numbers alone score 3, below threshold 4 → does not trigger."""
        query = "①调研市场数据 ②分析竞品策略 ③撰写报告 ④制定方案" + "x" * 30
        assert should_suggest_workflow(query, routing_tier="reasoning") is False

    def test_detects_step_keywords(self):
        query = (
            "第一步收集数据，第二步分析趋势，第三步生成报告，"
            "然后分别对比各个竞品的优劣势，给出推荐"
        )
        assert should_suggest_workflow(query, routing_tier="reasoning") is True

    def test_detects_parallel_keywords(self):
        query = (
            "调研 5 家竞品，分别分析各家的优劣势，"
            "每家写一份对比报告，最终给出推荐方案和总结，"
            "要求全面且深入"
        )
        assert should_suggest_workflow(query, routing_tier="reasoning") is True

    def test_multimodal_content_extraction(self):
        content = [
            {"type": "text", "text": MULTI_GOAL_QUERY},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}},
        ]
        assert should_suggest_workflow(content, routing_tier="reasoning") is True

    def test_multimodal_only_image_rejects(self):
        content = [
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}},
        ]
        assert should_suggest_workflow(content, routing_tier="reasoning") is False


# ---------------------------------------------------------------------------
# should_suggest_workflow_for_session() — session-aware guard
# ---------------------------------------------------------------------------


class TestShouldSuggestWorkflowForSession:
    """Session-aware guard — verifies default-off gatekeeping."""

    def test_default_extra_context_blocks(self):
        """Empty extra_context → suggest_workflow_mode defaults to False → blocked."""
        session = _make_session(
            query=MULTI_GOAL_QUERY,
            routing_tier="reasoning",
            extra_context={},
        )
        assert should_suggest_workflow_for_session(session) is False

    def test_explicit_false_blocks(self):
        session = _make_session(
            query=MULTI_GOAL_QUERY,
            routing_tier="reasoning",
            extra_context={"suggest_workflow_mode": False},
        )
        assert should_suggest_workflow_for_session(session) is False

    def test_explicit_true_allows_detection(self):
        """User explicitly opted in → detection proceeds normally."""
        session = _make_session(
            query=MULTI_GOAL_QUERY,
            routing_tier="reasoning",
            extra_context={"suggest_workflow_mode": True},
        )
        assert should_suggest_workflow_for_session(session) is True

    def test_opt_in_with_simple_query_still_rejects(self):
        """Even with opt-in, simple queries don't trigger suggestion."""
        session = _make_session(
            query=SIMPLE_QUERY,
            routing_tier="reasoning",
            extra_context={"suggest_workflow_mode": True},
        )
        assert should_suggest_workflow_for_session(session) is False

    def test_skip_flag_overrides_opt_in(self):
        """skipWorkflowSuggestion in engine_params overrides user opt-in."""
        session = _make_session(
            query=MULTI_GOAL_QUERY,
            routing_tier="reasoning",
            extra_context={"suggest_workflow_mode": True},
            engine_params={"skipWorkflowSuggestion": True},
        )
        assert should_suggest_workflow_for_session(session) is False

    def test_opt_in_non_reasoning_tier_rejects(self):
        """Even with opt-in, non-reasoning tier rejects."""
        session = _make_session(
            query=MULTI_GOAL_QUERY,
            routing_tier="fast",
            extra_context={"suggest_workflow_mode": True},
        )
        assert should_suggest_workflow_for_session(session) is False

    def test_none_engine_params_does_not_crash(self):
        """engine_params=None should not cause AttributeError."""
        session = _make_session(
            query=MULTI_GOAL_QUERY,
            routing_tier="reasoning",
            extra_context={"suggest_workflow_mode": True},
            engine_params=None,
        )
        assert should_suggest_workflow_for_session(session) is True

    def test_empty_engine_params_allows(self):
        """Empty engine_params dict should not block suggestion."""
        session = _make_session(
            query=MULTI_GOAL_QUERY,
            routing_tier="reasoning",
            extra_context={"suggest_workflow_mode": True},
            engine_params={},
        )
        assert should_suggest_workflow_for_session(session) is True

    def test_truthy_non_bool_value_blocks(self):
        """Non-bool truthy value (e.g. int 0) should be treated as falsy."""
        session = _make_session(
            query=MULTI_GOAL_QUERY,
            routing_tier="reasoning",
            extra_context={"suggest_workflow_mode": 0},
        )
        assert should_suggest_workflow_for_session(session) is False

    def test_truthy_int_one_allows(self):
        """Non-bool truthy value (int 1) should be treated as truthy."""
        session = _make_session(
            query=MULTI_GOAL_QUERY,
            routing_tier="reasoning",
            extra_context={"suggest_workflow_mode": 1},
        )
        assert should_suggest_workflow_for_session(session) is True

    def test_simple_routing_tier_rejects(self):
        """routing_tier='simple' should be rejected like 'fast'."""
        session = _make_session(
            query=MULTI_GOAL_QUERY,
            routing_tier="simple",
            extra_context={"suggest_workflow_mode": True},
        )
        assert should_suggest_workflow_for_session(session) is False


# ---------------------------------------------------------------------------
# _extract_text() — text extraction edge cases
# ---------------------------------------------------------------------------


class TestExtractText:
    """Edge cases for multimodal content text extraction."""

    def test_empty_list_returns_empty(self):
        from app.services.agent.stream_session.workflow_escalation import _extract_text
        assert _extract_text([]) == ""

    def test_dict_without_text_key_ignored(self):
        from app.services.agent.stream_session.workflow_escalation import _extract_text
        content = [{"type": "image_url", "url": "http://example.com"}]
        assert _extract_text(content) == ""

    def test_multiple_text_blocks_joined(self):
        from app.services.agent.stream_session.workflow_escalation import _extract_text
        content = [
            {"type": "text", "text": "Part A"},
            {"type": "text", "text": "Part B"},
        ]
        assert _extract_text(content) == "Part A Part B"

    def test_string_passthrough(self):
        from app.services.agent.stream_session.workflow_escalation import _extract_text
        assert _extract_text("hello world") == "hello world"
