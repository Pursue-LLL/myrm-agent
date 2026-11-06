"""Static guards for web_fetch_tool description (locale SSOT)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from myrm_agent_harness.agent._internals._agent_build import _weave_dynamic_schemas
from myrm_agent_harness.toolkits.browser.tools.navigate import create_navigate_tool
from myrm_agent_harness.toolkits.web_fetch._web_fetch_tool_description import (
    DEFAULT_WEB_FETCH_TOOL_DESCRIPTION_LOCALE,
    resolve_web_fetch_tool_description,
)
from myrm_agent_harness.toolkits.web_fetch.web_fetch_agent_tools import (
    create_web_fetch_tool,
)

_LOCALES = ("en", "zh-CN")


def test_default_locale_is_english() -> None:
    assert DEFAULT_WEB_FETCH_TOOL_DESCRIPTION_LOCALE == "en"
    assert resolve_web_fetch_tool_description(False) == (resolve_web_fetch_tool_description(False, None))


def test_web_fetch_tool_description_preserves_operation_guardrails_en() -> None:
    desc = resolve_web_fetch_tool_description(True, "en")
    required_fragments = (
        "fetch_and_extract",
        "Query rewriting rules",
        "mp.weixin.qq.com",
    )
    for fragment in required_fragments:
        assert fragment in desc, f"missing operation guardrail fragment: {fragment!r}"


def test_web_fetch_tool_description_preserves_operation_guardrails_zh() -> None:
    desc = resolve_web_fetch_tool_description(True, "zh-CN")
    required_fragments = (
        "fetch_and_extract",
        "query 改写规则",
        "mp.weixin.qq.com",
    )
    for fragment in required_fragments:
        assert fragment in desc, f"missing operation guardrail fragment: {fragment!r}"


def test_every_mode_explains_that_long_pages_are_shortened() -> None:
    """Both modes end in the same full read, which cuts long pages; the model must be told how to read on."""
    for enable_extract in (False, True):
        assert "Long pages come back shortened" in resolve_web_fetch_tool_description(enable_extract, "en")
        assert "过长的页面会被截短返回" in resolve_web_fetch_tool_description(enable_extract, "zh-CN")


def test_description_never_points_at_browser_tools() -> None:
    """Routing between reading and browsing lives on the navigation tool, so this text never dangles without it."""
    for enable_extract in (False, True):
        for locale in (None, *_LOCALES):
            desc = resolve_web_fetch_tool_description(enable_extract, locale)
            assert "browser" not in desc.lower(), f"dangling browser reference ({enable_extract=}, {locale=})"
            assert "浏览器" not in desc, f"dangling browser reference ({enable_extract=}, {locale=})"


def test_web_fetch_tool_description_never_leaks_policy_details() -> None:
    """Blocklist/decontamination internals must never reach the LLM prompt."""
    for enable_extract in (False, True):
        for locale in (None, "en", "zh-CN"):
            desc = resolve_web_fetch_tool_description(enable_extract, locale)
            for leaked in ("blocked", "decontam", "Hugging Face", "benchmark"):
                assert leaked not in desc, f"policy implementation detail leaked into prompt: {leaked!r}"


def test_plain_mode_describes_only_what_the_schema_accepts() -> None:
    """Without extract capability the tool has no ``operation`` argument, so the description must not name one."""
    limit = create_web_fetch_tool().args_schema.model_json_schema()["properties"]["urls"]["maxItems"]
    for locale, limit_phrase in (("en", f"up to {limit}"), ("zh-CN", f"最多 {limit} 个")):
        desc = resolve_web_fetch_tool_description(False, locale)
        assert "fetch_and_extract" not in desc
        assert "fetch_full_content" not in desc
        assert "operation" not in desc.lower()
        assert limit_phrase in desc, "the per-call URL limit must be stated and match the schema"


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


def test_plain_tool_urls_field_forbids_inventing_urls_and_states_the_limit() -> None:
    urls = create_web_fetch_tool().args_schema.model_json_schema()["properties"]["urls"]
    assert "never invent URLs" in urls["description"]
    assert f"up to {urls['maxItems']}" in urls["description"]


def test_create_web_fetch_tool_default_english_description() -> None:
    tool = create_web_fetch_tool()
    assert _weave_dynamic_schemas([tool])[0].description == resolve_web_fetch_tool_description(False, "en")


def test_create_web_fetch_tool_chinese_locale() -> None:
    tool = create_web_fetch_tool(description_locale="zh-CN")
    woven = _weave_dynamic_schemas([tool])[0]
    assert woven.description == resolve_web_fetch_tool_description(False, "zh-CN")
    assert woven.description.startswith("获取已知 URL 的完整内容")


@pytest.mark.parametrize("enable_extract", [False, True])
def test_every_mode_names_the_document_formats_it_reads(enable_extract: bool) -> None:
    """Without this sentence the model detours through bash to read a document the tool handles natively."""
    assert "PDF, DOCX, XLSX and PPTX" in resolve_web_fetch_tool_description(enable_extract, "en")
    assert "PDF、DOCX、XLSX、PPTX" in resolve_web_fetch_tool_description(enable_extract, "zh-CN")


def test_navigation_tool_routes_read_only_reads_to_web_fetch_only_while_it_is_mounted() -> None:
    """The web_fetch description carries no routing text, so this dynamic hint is the only guard against browsing for plain reads."""
    navigate = create_navigate_tool(MagicMock())
    web_fetch = create_web_fetch_tool()

    alone = _weave_dynamic_schemas([navigate])[0].description
    with_fetch = _weave_dynamic_schemas([navigate, web_fetch])[0].description

    assert web_fetch.name not in alone
    assert f"prefer {web_fetch.name}" in with_fetch
    assert "no interaction needed" in with_fetch
