"""Server wiring for harness tool description locale."""

from __future__ import annotations

from app.core.agent.tool_description_locale import resolve_tool_description_locale


def test_resolve_tool_description_locale_prefers_agent_locale() -> None:
    assert (
        resolve_tool_description_locale(agent_locale="zh-CN", channel="web_chat")
        == "zh-CN"
    )


def test_resolve_tool_description_locale_channel_default_for_im() -> None:
    assert resolve_tool_description_locale(channel="feishu") == "zh-CN"


def test_resolve_tool_description_locale_defaults_to_english() -> None:
    assert resolve_tool_description_locale(channel="web_chat") == "en"
