"""Tests for server tool layer registration in _tool_layer_bootstrap.py."""

from __future__ import annotations

from app.ai_agents.general_agent.tools._tool_layer_bootstrap import (
    ToolLayer,
    _SERVER_TOOL_LAYERS,
)


class TestServerToolLayerRegistration:
    def test_x_search_tool_registered(self) -> None:
        assert _SERVER_TOOL_LAYERS.get("x_search_tool") == ToolLayer.EXTENDED

    def test_channel_notify_tool_registered(self) -> None:
        assert _SERVER_TOOL_LAYERS.get("channel_notify_tool") == ToolLayer.EXTENDED

    def test_channel_notify_tool_leaf_blocked_for_subagents(self) -> None:
        from myrm_agent_harness.agent.sub_agents.delegation_policy import get_effective_leaf_blocked_tools
        from myrm_agent_harness.agent.sub_agents.types import DELEGATION_CAPABILITY_MANIFEST

        effective = get_effective_leaf_blocked_tools(DELEGATION_CAPABILITY_MANIFEST.leaf_blocked_tools)
        assert "channel_notify_tool" in effective

    def test_media_tools_registered(self) -> None:
        for name in ("image_tool", "video_tool", "tts_generate"):
            assert _SERVER_TOOL_LAYERS.get(name) == ToolLayer.EXTENDED, name

    def test_browser_local_search_not_registered(self) -> None:
        assert "browser_local_search_tool" not in _SERVER_TOOL_LAYERS
