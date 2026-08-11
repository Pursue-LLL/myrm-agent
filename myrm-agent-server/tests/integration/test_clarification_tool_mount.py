"""Integration: ask_question_tool mount policy for interactive web vs unattended/IM."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.ai_agents.agents import AgentFactory, GeneralAgentParams
from app.ai_agents.general_agent.tool_setup import (
    ToolSetupMixin,
    _should_mount_ask_question_tool,
)
from app.core.types import ModelConfig


def _tool_names(items: list[object]) -> set[str]:
    return {name for tool in items if (name := getattr(tool, "name", None))}


def _make_mixin(**overrides: object) -> ToolSetupMixin:
    mixin = ToolSetupMixin.__new__(ToolSetupMixin)
    defaults: dict[str, object] = {
        "enable_web_search": False,
        "search_service_cfg": None,
        "reranker_config": None,
        "enable_advanced_retrieval": False,
        "embedding_config": None,
        "fetch_raw_webpage": False,
        "enable_render_ui": False,
        "image_generation_params": None,
        "video_generation_params": None,
        "tts_params": None,
        "search_depth": "normal",
        "model_cfg": MagicMock(model="test-model", api_key="k", base_url="http://localhost"),
        "skill_ids": [],
        "unattended_mode": False,
        "channel_name": "web_chat",
        "prompt_mode": "full",
        "enable_structured_clarify": True,
    }
    defaults.update(overrides)
    for key, value in defaults.items():
        setattr(mixin, key, value)
    return mixin


def test_should_mount_predicate_matrix() -> None:
    assert _should_mount_ask_question_tool(
        unattended_mode=False,
        channel_name="web_chat",
        prompt_mode="full",
        enable_structured_clarify=True,
    )
    assert not _should_mount_ask_question_tool(
        unattended_mode=True,
        channel_name="web_chat",
        prompt_mode="full",
        enable_structured_clarify=True,
    )
    assert not _should_mount_ask_question_tool(
        unattended_mode=False,
        channel_name="telegram_instance_1",
        prompt_mode="full",
        enable_structured_clarify=True,
    )
    assert not _should_mount_ask_question_tool(
        unattended_mode=False,
        channel_name="web_chat",
        prompt_mode="search",
        enable_structured_clarify=True,
    )
    assert not _should_mount_ask_question_tool(
        unattended_mode=False,
        channel_name="web_chat",
        prompt_mode="full",
        enable_structured_clarify=False,
    )


def test_ask_question_mounted_for_interactive_web_chat() -> None:
    mixin = _make_mixin()
    tools: list[object] = []
    mixin._setup_clarification_tools(tools)

    assert "ask_question_tool" in _tool_names(tools)


def test_ask_question_tool_schema_uses_requires_confirmation() -> None:
    """Mounted tool must expose requires_confirmation (not legacy clarification_type)."""
    from myrm_agent_harness.agent.meta_tools.clarification.ask_question import AskQuestionInput

    mixin = _make_mixin()
    tools: list[object] = []
    mixin._setup_clarification_tools(tools)

    ask_tool = next(tool for tool in tools if getattr(tool, "name", None) == "ask_question_tool")
    assert ask_tool.args_schema is AskQuestionInput

    properties = AskQuestionInput.model_json_schema()["properties"]
    assert "requires_confirmation" in properties
    assert "clarification_type" not in properties


def test_ask_question_skipped_when_unattended() -> None:
    mixin = _make_mixin(unattended_mode=True)
    tools: list[object] = []
    mixin._setup_clarification_tools(tools)

    assert "ask_question_tool" not in _tool_names(tools)


def test_ask_question_skipped_for_im_channel() -> None:
    mixin = _make_mixin(channel_name="telegram_abc123")
    tools: list[object] = []
    mixin._setup_clarification_tools(tools)

    assert "ask_question_tool" not in _tool_names(tools)


def test_ask_question_skipped_when_structured_clarify_disabled() -> None:
    mixin = _make_mixin(enable_structured_clarify=False)
    tools: list[object] = []
    mixin._setup_clarification_tools(tools)

    assert "ask_question_tool" not in _tool_names(tools)


def test_factory_unattended_agent_excludes_ask_question_tool() -> None:
    params = GeneralAgentParams(
        query="test",
        model_cfg=ModelConfig(model="test/model", api_key="test-key"),
        unattended_mode=True,
        channel_name="cron",
        prompt_mode="full",
    )
    agent = AgentFactory.create_general_agent(params)
    assert agent.unattended_mode is True

    tools: list[object] = []
    agent._setup_clarification_tools(tools)

    assert "ask_question_tool" not in _tool_names(tools)
