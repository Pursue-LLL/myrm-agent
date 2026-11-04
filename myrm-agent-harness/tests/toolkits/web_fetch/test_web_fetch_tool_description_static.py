"""Static guards for web_fetch_tool description (locale SSOT)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from myrm_agent_harness.toolkits.web_fetch._web_fetch_tool_description import (
    DEFAULT_WEB_FETCH_TOOL_DESCRIPTION_LOCALE,
    resolve_web_fetch_tool_description,
)
from myrm_agent_harness.toolkits.web_fetch.web_fetch_agent_tools import (
    create_web_fetch_tool,
)


def test_default_locale_is_english() -> None:
    assert DEFAULT_WEB_FETCH_TOOL_DESCRIPTION_LOCALE == "en"
    assert resolve_web_fetch_tool_description(False) == (resolve_web_fetch_tool_description(False, None))


def test_web_fetch_tool_description_preserves_operation_guardrails_en() -> None:
    desc = resolve_web_fetch_tool_description(True, "en")
    required_fragments = (
        "fetch_and_extract",
        "Query rewriting rules",
        "handles JS rendering internally",
        "mp.weixin.qq.com",
        "For JS-heavy or interactive pages (clicking, filling forms, scrolling), use browser tools",
    )
    for fragment in required_fragments:
        assert fragment in desc, f"missing operation guardrail fragment: {fragment!r}"


def test_web_fetch_tool_description_preserves_operation_guardrails_zh() -> None:
    desc = resolve_web_fetch_tool_description(True, "zh-CN")
    required_fragments = (
        "fetch_and_extract",
        "query 改写规则",
        "内部处理 JS 渲染",
        "mp.weixin.qq.com",
        "点击、填表、滚动",
    )
    for fragment in required_fragments:
        assert fragment in desc, f"missing operation guardrail fragment: {fragment!r}"


def test_web_fetch_tool_description_never_leaks_policy_details() -> None:
    """Blocklist/decontamination internals must never reach the LLM prompt."""
    for enable_extract in (False, True):
        for locale in (None, "en", "zh-CN"):
            desc = resolve_web_fetch_tool_description(enable_extract, locale)
            for leaked in ("blocked", "decontam", "Hugging Face", "benchmark"):
                assert leaked not in desc, f"policy implementation detail leaked into prompt: {leaked!r}"


def test_plain_mode_describes_only_what_the_schema_accepts() -> None:
    """Without extract capability the tool has no ``operation`` argument, so the description must not name one."""
    for locale in ("en", "zh-CN"):
        desc = resolve_web_fetch_tool_description(False, locale)
        assert "fetch_and_extract" not in desc
        assert "fetch_full_content" not in desc
        assert "operation" not in desc.lower()
        assert "5" in desc, "the per-call URL limit must be stated"


def test_extract_mode_keeps_naming_both_operations() -> None:
    en = resolve_web_fetch_tool_description(True, "en")
    zh = resolve_web_fetch_tool_description(True, "zh-CN")
    for desc in (en, zh):
        assert 'operation: "fetch_full_content"' in desc or 'operation："fetch_full_content"' in desc
        assert 'operation: "fetch_and_extract"' in desc or 'operation："fetch_and_extract"' in desc
    assert "are supported via fetch_full_content;" in en
    assert "可通过 fetch_full_content 获取；" in zh


def test_plain_tool_schema_takes_urls_and_reason_only() -> None:
    schema = create_web_fetch_tool().args_schema.model_json_schema()

    assert set(schema["properties"]) == {"urls", "reason"}
    assert set(schema["required"]) == {"urls", "reason"}
    assert (schema["properties"]["urls"]["minItems"], schema["properties"]["urls"]["maxItems"]) == (1, 5)


def test_extract_tool_schema_keeps_operation_and_questions() -> None:
    schema = create_web_fetch_tool(MagicMock(), MagicMock()).args_schema.model_json_schema()

    assert set(schema["properties"]) == {"urls", "operation", "questions", "reason"}
    assert schema["properties"]["operation"]["default"] == "fetch_and_extract"
    assert schema["properties"]["questions"]["maxItems"] == 5
    assert "maxItems" not in schema["properties"]["urls"]


@pytest.mark.asyncio
async def test_plain_tool_refuses_more_urls_than_its_limit() -> None:
    tool = create_web_fetch_tool()
    urls = [f"https://example.com/{i}" for i in range(6)]

    with pytest.raises(ValidationError):
        await tool.ainvoke({"urls": urls, "reason": "too many"})


def test_create_web_fetch_tool_default_english_description() -> None:
    tool = create_web_fetch_tool()
    assert tool.description == resolve_web_fetch_tool_description(False, "en")


def test_create_web_fetch_tool_chinese_locale() -> None:
    tool = create_web_fetch_tool(description_locale="zh-CN")
    assert tool.description == resolve_web_fetch_tool_description(False, "zh-CN")
    assert tool.description.startswith("web_fetch_tool 从指定的网页 URL")
