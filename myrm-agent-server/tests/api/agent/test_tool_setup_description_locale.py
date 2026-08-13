"""Tool setup forwards the resolved description locale into web_fetch_tool.

The harness exposes bilingual (en/zh) LLM tool descriptions; the server bridge
``resolve_tool_description_locale`` binds the agent/channel locale, and the
web_fetch baseline tool must receive it so its schema stays in the user's
language. This guards the Turn1 schema-locale contract (same as web_search).
"""

from __future__ import annotations

from unittest.mock import patch

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
    enable_render_ui = False


def test_web_fetch_tool_receives_resolved_description_locale() -> None:
    with (
        patch("myrm_agent_harness.toolkits.create_web_fetch_tool") as mock_create,
        patch.object(ToolSetupMixin, "_setup_x_live_search_tool"),
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
        patch.object(ToolSetupMixin, "_setup_x_live_search_tool"),
        patch.object(ToolSetupMixin, "_setup_image_generation_tools"),
        patch.object(ToolSetupMixin, "_setup_video_generation_tools"),
        patch.object(ToolSetupMixin, "_setup_tts_tools"),
    ):
        tools: list[object] = []
        _EnglishStub()._setup_search_and_basic_tools(tools)

    assert mock_create.call_count == 1
    assert mock_create.call_args.kwargs["description_locale"] == "en"
