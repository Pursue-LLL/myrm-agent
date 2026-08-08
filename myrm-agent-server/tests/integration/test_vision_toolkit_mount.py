"""Integration: vision-toolkit skill mounts EXTENDED vision tools."""

from __future__ import annotations

from app.ai_agents.general_agent.tool_setup import ToolSetupMixin
from app.core.types import ModelConfig


class _MemExecutor:
    async def read_file_bytes(self, path: str) -> bytes:
        return b""


def test_vision_toolkit_mounts_semantic_and_geometry_tools() -> None:
    mixin = ToolSetupMixin.__new__(ToolSetupMixin)
    mixin.executor = _MemExecutor()
    mixin.vision_fallback_model_cfg = ModelConfig(model="gpt-4o-mini", api_key="sk-test")
    mixin.vision_fallback_model_cfgs = [mixin.vision_fallback_model_cfg]

    tools: list[object] = []
    mixin._setup_vision_toolkit_tools(tools)

    names = {getattr(tool, "name", None) for tool in tools}
    assert "vision_semantic_tool" in names
    assert "vision_geometry_tool" in names


def test_vision_toolkit_skips_without_fallback_config() -> None:
    mixin = ToolSetupMixin.__new__(ToolSetupMixin)
    mixin.executor = _MemExecutor()
    mixin.vision_fallback_model_cfg = None
    mixin.vision_fallback_model_cfgs = None

    tools: list[object] = []
    mixin._setup_vision_toolkit_tools(tools)

    assert tools == []
