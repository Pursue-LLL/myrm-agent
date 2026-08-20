"""Server wiring for harness tool description locale."""

from __future__ import annotations

from myrm_agent_harness.toolkits.memory._memory_agent_tool_descriptions import (
    resolve_memory_save_tool_description,
)

from app.core.agent.tool_description_locale import (
    resolve_agent_params_locale,
    resolve_tool_description_locale,
)


def test_resolve_tool_description_locale_prefers_agent_locale() -> None:
    assert resolve_tool_description_locale(agent_locale="zh-CN", channel="web_chat") == "zh-CN"


def test_resolve_tool_description_locale_channel_default_for_im() -> None:
    assert resolve_tool_description_locale(channel="feishu") == "zh-CN"


def test_resolve_tool_description_locale_defaults_to_english() -> None:
    assert resolve_tool_description_locale(channel="web_chat") == "en"


def test_resolve_agent_params_locale_reads_personal_settings_locale_key() -> None:
    assert (
        resolve_agent_params_locale(
            personal_settings={"locale": "zh-CN"},
            channel="web_chat",
        )
        == "zh-CN"
    )


def test_resolve_agent_params_locale_falls_back_to_language_key() -> None:
    assert (
        resolve_agent_params_locale(
            personal_settings={"language": "zh-CN"},
            channel="cron",
        )
        == "zh-CN"
    )


def test_zh_cn_locale_yields_chinese_memory_save_description() -> None:
    locale = resolve_agent_params_locale(
        personal_settings={"locale": "zh-CN"},
        channel="web_chat",
    )
    description = resolve_memory_save_tool_description(locale)
    assert "何时保存" in description
