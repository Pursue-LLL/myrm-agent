"""Integration: enable_web_fetch gate real tool_setup wiring (no mocks on gate path)."""

from __future__ import annotations

from langchain_core.tools import BaseTool

from app.ai_agents.general_agent.tool_setup import ToolSetupMixin
from app.core.types import ModelConfig


def _tool_names(tools: list[object]) -> list[str]:
    names: list[str] = []
    for tool in tools:
        if isinstance(tool, BaseTool):
            names.append(tool.name)
        else:
            names.append(getattr(tool, "name", str(tool)))
    return names


def _minimal_tool_setup_mixin(**overrides: object) -> ToolSetupMixin:
    mixin = ToolSetupMixin.__new__(ToolSetupMixin)
    defaults: dict[str, object] = {
        "enable_web_fetch": True,
        "enable_web_search": False,
        "search_service_cfg": None,
        "search_depth": "standard",
        "fetch_raw_webpage": False,
        "enable_advanced_retrieval": False,
        "reranker_config": None,
        "embedding_config": None,
        "enable_render_ui": False,
        "channel_name": "web_chat",
        "skill_ids": [],
        "model_cfg": ModelConfig(model="test/model", api_key="test-key"),
        "image_generation_params": None,
        "video_generation_params": None,
        "tts_params": None,
    }
    for key, value in defaults.items():
        setattr(mixin, key, value)
    for key, value in overrides.items():
        setattr(mixin, key, value)
    return mixin


def test_setup_search_omits_web_fetch_when_gate_false() -> None:
    mixin = _minimal_tool_setup_mixin(enable_web_fetch=False)
    tools: list[object] = []
    mixin._setup_search_and_basic_tools(tools)
    assert "web_fetch_tool" not in _tool_names(tools)


def test_setup_search_includes_web_fetch_when_gate_true() -> None:
    mixin = _minimal_tool_setup_mixin(enable_web_fetch=True)
    tools: list[object] = []
    mixin._setup_search_and_basic_tools(tools)
    assert "web_fetch_tool" in _tool_names(tools)
