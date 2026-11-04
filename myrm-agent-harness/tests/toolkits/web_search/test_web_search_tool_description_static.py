"""Static guards for web_search_tool description (query-rewrite SSOT)."""

from __future__ import annotations

import pytest

from myrm_agent_harness.toolkits.web_search._web_search_tool_description import (
    DEFAULT_WEB_SEARCH_TOOL_DESCRIPTION_LOCALE,
    resolve_web_search_tool_description,
)
from myrm_agent_harness.toolkits.web_search.engine import SearchServiceConfig
from myrm_agent_harness.toolkits.web_search.web_search_agent_tools import (
    create_web_search_tool,
)


def _search_cfg() -> SearchServiceConfig:
    return SearchServiceConfig(search_service="tavily", api_key="test-key")


def test_default_locale_is_english() -> None:
    assert DEFAULT_WEB_SEARCH_TOOL_DESCRIPTION_LOCALE == "en"
    assert resolve_web_search_tool_description() == resolve_web_search_tool_description("en")
    assert resolve_web_search_tool_description(None) == resolve_web_search_tool_description("en")


def test_web_search_tool_description_preserves_rewrite_guardrails_en() -> None:
    desc = resolve_web_search_tool_description("en", fetch_and_extract_available=True)
    required_fragments = (
        "Each query must be understandable on its own, outside the conversation and other queries",
        "abbreviations, codes, or short names that appear alone without context",
        "Do not produce synonymous rewrites",
        "a complex question may additionally include one synthesis query",
        "time_range: Set only when the user explicitly gives a time range",
        "use site: in the query to restrict domains",
        "If results do not cover key aspects needed to answer, prefer rewriting for missing aspects or adding complementary queries",
        "When an information request spans multiple domains or you are uncertain whether a query is general or vertical, use a hybrid strategy",
        "combine with web_fetch_tool's fetch_and_extract operation",
    )
    forbidden_fragments = (
        "依赖搜索提供商",
        "并非所有提供商",
        "Provider-dependent",
    )
    for fragment in required_fragments:
        assert fragment in desc, f"missing rewrite guardrail fragment: {fragment!r}"
    for fragment in forbidden_fragments:
        assert fragment not in desc, f"implementation detail leaked into prompt: {fragment!r}"


def test_web_search_tool_description_preserves_rewrite_guardrails_zh() -> None:
    desc = resolve_web_search_tool_description("zh-CN", fetch_and_extract_available=True)
    required_fragments = (
        "每条 query 脱离会话和其他 query 后都必须可理解",
        "补全单独出现且没有上下文的缩写、代号或短名称",
        "禁止同义改写或信息重叠",
        "复杂问题可额外加入一条综合 query",
        "time_range：仅当用户明确给出时间范围",
        "site:",
        "若结果没有覆盖回答所需的关键方面，优先改写缺失方面或增加互补 query",
        "采用混合策略：并行发起 1 条通用 query 与 1-2 条垂直领域针对性 query",
        "联动 web_fetch_tool 的 fetch_and_extract 操作提取清洗后的正文段落",
    )
    forbidden_fragments = (
        "Provider-dependent",
        "依赖搜索提供商",
    )
    for fragment in required_fragments:
        assert fragment in desc, f"missing rewrite guardrail fragment: {fragment!r}"
    for fragment in forbidden_fragments:
        assert fragment not in desc, f"implementation detail leaked into prompt: {fragment!r}"


@pytest.mark.parametrize("locale", ["en", "zh-CN"])
def test_fetch_and_extract_hint_appears_only_when_that_operation_exists(locale: str) -> None:
    """The hint is one line; without the operation nothing else in the description changes."""
    with_hint = resolve_web_search_tool_description(locale, fetch_and_extract_available=True)
    without_hint = resolve_web_search_tool_description(locale)

    assert with_hint.count("fetch_and_extract") == 1
    assert "fetch_and_extract" not in without_hint
    assert "web_fetch_tool" not in without_hint
    kept = [line for line in with_hint.split("\n") if "fetch_and_extract" not in line]
    assert kept == without_hint.split("\n")


def test_create_web_search_tool_default_english_description() -> None:
    tool = create_web_search_tool(search_service_cfg=_search_cfg())
    assert tool.description == resolve_web_search_tool_description("en")


def test_create_web_search_tool_recommends_extract_only_when_told_it_exists() -> None:
    tool = create_web_search_tool(search_service_cfg=_search_cfg(), fetch_and_extract_available=True)
    assert tool.description == resolve_web_search_tool_description("en", fetch_and_extract_available=True)
    assert "fetch_and_extract" in tool.description


def test_create_web_search_tool_chinese_locale() -> None:
    tool = create_web_search_tool(
        search_service_cfg=_search_cfg(),
        description_locale="zh-CN",
    )
    assert tool.description == resolve_web_search_tool_description("zh-CN")
    assert tool.description.startswith("web_search_tool 用于检索")
