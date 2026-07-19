"""Tests for knowledge_recall_tool mount gate in ToolSetupMixin."""

from __future__ import annotations

from unittest.mock import MagicMock

from langchain_core.tools import BaseTool

from app.ai_agents.general_agent.tool_setup import ToolSetupMixin


def _build_mixin(**overrides: object) -> ToolSetupMixin:
    mixin = ToolSetupMixin.__new__(ToolSetupMixin)
    defaults: dict[str, object] = {
        "enable_wiki": True,
        "enable_memory": True,
        "incognito_mode": False,
        "agent_id": "researcher",
        "_lite_llm": MagicMock(),
    }
    defaults.update(overrides)
    for key, value in defaults.items():
        setattr(mixin, key, value)
    return mixin


def test_mounts_when_wiki_and_memory_enabled() -> None:
    mixin = _build_mixin()
    tools: list[object] = []
    manager = MagicMock()

    mixin._setup_knowledge_recall_tool(tools, manager)

    assert len(tools) == 1
    assert isinstance(tools[0], BaseTool)
    assert tools[0].name == "knowledge_recall_tool"


def test_skips_when_wiki_disabled() -> None:
    mixin = _build_mixin(enable_wiki=False)
    tools: list[object] = []

    mixin._setup_knowledge_recall_tool(tools, MagicMock())

    assert tools == []


def test_skips_when_memory_disabled() -> None:
    mixin = _build_mixin(enable_memory=False)
    tools: list[object] = []

    mixin._setup_knowledge_recall_tool(tools, MagicMock())

    assert tools == []


def test_skips_in_incognito_mode() -> None:
    mixin = _build_mixin(incognito_mode=True)
    tools: list[object] = []

    mixin._setup_knowledge_recall_tool(tools, MagicMock())

    assert tools == []


def test_skips_without_lite_llm() -> None:
    mixin = _build_mixin(_lite_llm=None)
    tools: list[object] = []

    mixin._setup_knowledge_recall_tool(tools, MagicMock())

    assert tools == []
