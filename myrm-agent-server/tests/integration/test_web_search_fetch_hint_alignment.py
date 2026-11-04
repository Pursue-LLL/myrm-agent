"""Integration: web_search only recommends fetch_and_extract when the mounted web_fetch_tool really offers it."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from langchain_core.tools import BaseTool
from myrm_agent_harness.toolkits.web_search.engine import SearchServiceConfig

from app.ai_agents.general_agent.tool_setup import ToolSetupMixin
from app.core.types import ModelConfig


def _mixin(**overrides: object) -> ToolSetupMixin:
    mixin = ToolSetupMixin.__new__(ToolSetupMixin)
    defaults: dict[str, object] = {
        "enable_web_fetch": True,
        "enable_web_search": True,
        "search_service_cfg": SearchServiceConfig(search_service="tavily", api_key="test-key"),
        "search_depth": "standard",
        "fetch_raw_webpage": False,
        "enable_advanced_retrieval": False,
        "reranker_config": None,
        "embedding_config": None,
        "channel_name": "web_chat",
        "skill_ids": [],
        "model_cfg": ModelConfig(model="test/model", api_key="test-key"),
        "image_generation_params": None,
        "video_generation_params": None,
        "tts_params": None,
    }
    for key, value in {**defaults, **overrides}.items():
        setattr(mixin, key, value)
    return mixin


def _mounted(mixin: ToolSetupMixin) -> dict[str, BaseTool]:
    tools: list[object] = []
    mixin._setup_search_and_basic_tools(tools)
    return {tool.name: tool for tool in tools if isinstance(tool, BaseTool)}


@pytest.mark.parametrize(
    ("overrides", "extract_offered"),
    [
        pytest.param({}, False, id="advanced-retrieval-off"),
        pytest.param({"enable_advanced_retrieval": True}, False, id="advanced-on-without-configs"),
        pytest.param(
            {"enable_advanced_retrieval": True, "reranker_config": MagicMock()},
            False,
            id="advanced-on-reranker-only",
        ),
        pytest.param(
            {"enable_advanced_retrieval": True, "embedding_config": MagicMock()},
            False,
            id="advanced-on-embedding-only",
        ),
        pytest.param(
            {"enable_advanced_retrieval": True, "reranker_config": MagicMock(), "embedding_config": MagicMock()},
            True,
            id="advanced-on-with-both-configs",
        ),
        pytest.param(
            {"enable_advanced_retrieval": False, "reranker_config": MagicMock(), "embedding_config": MagicMock()},
            False,
            id="configs-present-but-advanced-off",
        ),
    ],
)
def test_search_recommends_extract_exactly_when_fetch_offers_it(overrides: dict[str, object], extract_offered: bool) -> None:
    tools = _mounted(_mixin(**overrides))

    fetch_offers_extract = "operation" in tools["web_fetch_tool"].args_schema.model_json_schema()["properties"]
    assert fetch_offers_extract is extract_offered
    assert ("fetch_and_extract" in tools["web_search_tool"].description) is extract_offered


def test_search_never_mentions_fetch_when_web_fetch_is_not_mounted() -> None:
    tools = _mounted(
        _mixin(
            enable_web_fetch=False,
            enable_advanced_retrieval=True,
            reranker_config=MagicMock(),
            embedding_config=MagicMock(),
        )
    )

    assert "web_fetch_tool" not in tools
    assert "fetch_and_extract" not in tools["web_search_tool"].description
    assert "web_fetch_tool" not in tools["web_search_tool"].description
