"""Tool setup forwards the session's description locale into the tools that come in two languages.

The harness exposes bilingual (en/zh) LLM tool descriptions; the host's ``_tool_description_locale`` binds the agent,
prompt and channel locale, and a tool setup that does not hand it to its factory shows every session the English text.
web_fetch_tool is checked at the factory call (the Turn1 schema-locale contract, same as web_search); the skill market
and manage tools by the descriptions they end up with.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from myrm_agent_harness.agent.meta_tools.skills.manage.skill_manage_tool import resolve_skill_manage_tool_description
from myrm_agent_harness.agent.meta_tools.skills.market.skill_market_tool import resolve_skill_market_tool_description

from app.ai_agents.general_agent.tool_setup import ToolSetupMixin


class _Stub(ToolSetupMixin):
    """Minimal mixin stand-in exposing only the attrs ``_setup_search_and_basic_tools`` reads."""

    locale = "zh-CN"
    channel_name = None
    enable_web_fetch = True
    fetch_raw_webpage = False
    enable_advanced_retrieval = False
    reranker_config = None
    embedding_config = None
    search_depth = "basic"
    enable_web_search = False
    search_service_cfg = None
    model_cfg = None
    skill_ids = None


def test_web_fetch_tool_receives_resolved_description_locale() -> None:
    with (
        patch("myrm_agent_harness.toolkits.create_web_fetch_tool") as mock_create,
        patch.object(ToolSetupMixin, "_setup_image_generation_tools"),
        patch.object(ToolSetupMixin, "_setup_video_generation_tools"),
        patch.object(ToolSetupMixin, "_setup_tts_tools"),
    ):
        tools: list[object] = []
        _Stub()._setup_search_and_basic_tools(tools)

    assert mock_create.call_count == 1
    assert mock_create.call_args.kwargs["description_locale"] == "zh-CN"


def test_web_fetch_tool_description_locale_defaults_to_english() -> None:
    class _EnglishStub(_Stub):
        locale = None
        channel_name = "web"

    with (
        patch("myrm_agent_harness.toolkits.create_web_fetch_tool") as mock_create,
        patch.object(ToolSetupMixin, "_setup_image_generation_tools"),
        patch.object(ToolSetupMixin, "_setup_video_generation_tools"),
        patch.object(ToolSetupMixin, "_setup_tts_tools"),
    ):
        tools: list[object] = []
        _EnglishStub()._setup_search_and_basic_tools(tools)

    assert mock_create.call_count == 1
    assert mock_create.call_args.kwargs["description_locale"] == "en"


class _SkillHost(ToolSetupMixin):
    """Minimal mixin stand-in exposing only the attrs the skill market and manage setups read."""

    enable_skill_manage = True
    force_skill_manage = False
    locale: str | None = None
    prompt_locale: str | None = None
    channel_name: str | None = None


@pytest.mark.parametrize(
    ("locale", "prompt_locale", "channel", "described_in"),
    [
        pytest.param("zh-CN", None, "web_chat", "zh-CN", id="chinese-session"),
        pytest.param(None, None, "feishu", "zh-CN", id="im-channel-without-a-session-language"),
        pytest.param("en", None, "feishu", "en", id="english-session-on-an-im-channel"),
        pytest.param("en", "zh-CN", "web_chat", "zh-CN", id="prompt-locale-leads"),
        pytest.param("fr", None, "web_chat", "en", id="language-without-a-translation"),
        pytest.param(None, None, "web_chat", "en", id="no-language-at-all"),
    ],
)
def test_skill_tools_are_described_in_the_language_of_the_session(
    monkeypatch: pytest.MonkeyPatch, locale: str | None, prompt_locale: str | None, channel: str, described_in: str
) -> None:
    monkeypatch.delenv("MYRM_LOCALE", raising=False)
    host = _SkillHost()
    host.locale, host.prompt_locale, host.channel_name = locale, prompt_locale, channel
    tools: list[object] = []

    host._setup_skill_market_tool(tools, SimpleNamespace(install_from_url=object(), uninstall=object()))
    host._setup_skill_manage_tool(tools, object(), object())

    descriptions = {tool.name: tool.description for tool in tools}
    # The market tool appends its cross-tool hints after the text, and the framework trims the text's trailing newline.
    assert descriptions["skill_market_tool"].startswith(resolve_skill_market_tool_description(described_in).strip())
    assert descriptions["skill_manage_tool"].startswith(resolve_skill_manage_tool_description(described_in).strip())
