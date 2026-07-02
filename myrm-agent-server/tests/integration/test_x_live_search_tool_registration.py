"""Integration test: x-live-search skill-gated eager tool registration.

Verifies _setup_x_live_search_tool() loads x_search_tool into Turn1 tools when the
x-live-search prebuilt skill is enabled, independent of enable_web_search.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.core.skills.oauth_availability import X_LIVE_SEARCH_SKILL_ID


def _make_search_mixin(*, skill_ids: list[str] | None) -> object:
    from app.ai_agents.general_agent.tool_setup import ToolSetupMixin

    mixin = ToolSetupMixin.__new__(ToolSetupMixin)
    mixin.enable_web_search = True
    mixin.search_service_cfg = MagicMock()
    mixin.reranker_config = None
    mixin.enable_advanced_retrieval = False
    mixin.embedding_config = None
    mixin.fetch_raw_webpage = False
    mixin.enable_render_ui = False
    mixin.image_generation_params = None
    mixin.video_generation_params = None
    mixin.tts_params = None
    mixin.search_depth = "normal"
    mixin.model_cfg = MagicMock(model="test-model", api_key="k", base_url="http://localhost")
    mixin.skill_ids = skill_ids or []
    return mixin


def test_x_search_tool_registers_when_skill_enabled() -> None:
    """x_search_tool must land in Turn1 tools when skill is bound."""
    mixin = _make_search_mixin(skill_ids=[X_LIVE_SEARCH_SKILL_ID])
    tools: list[object] = []
    deferred_tools: list[object] = []

    with patch("app.config.deploy_mode.is_local_mode", return_value=True):
        mixin._setup_search_and_basic_tools(tools, deferred_tools)

    assert any(getattr(t, "name", None) == "x_search_tool" for t in tools)
    assert not any(getattr(t, "name", None) == "x_search_tool" for t in deferred_tools)


def test_x_search_tool_skipped_without_skill() -> None:
    """Without x-live-search skill, x_search_tool must not register at all."""
    mixin = _make_search_mixin(skill_ids=[])
    tools: list[object] = []
    deferred_tools: list[object] = []

    with patch("app.config.deploy_mode.is_local_mode", return_value=True):
        mixin._setup_search_and_basic_tools(tools, deferred_tools)

    assert not any(getattr(t, "name", None) == "x_search_tool" for t in deferred_tools)
    assert not any(getattr(t, "name", None) == "x_search_tool" for t in tools)


def test_x_search_tool_registers_when_web_search_disabled() -> None:
    """x_search_tool must register from skill alone — no Tavily/Brave web search required."""
    mixin = _make_search_mixin(skill_ids=[X_LIVE_SEARCH_SKILL_ID])
    mixin.enable_web_search = False
    mixin.search_service_cfg = None
    tools: list[object] = []
    deferred_tools: list[object] = []

    mixin._setup_search_and_basic_tools(tools, deferred_tools)

    assert any(getattr(t, "name", None) == "x_search_tool" for t in tools)
    assert not any(getattr(t, "name", None) == "x_search_tool" for t in deferred_tools)
    assert not any(getattr(t, "name", None) == "web_search_tool" for t in tools)
