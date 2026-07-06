"""Tests for server tool layer registration in _tool_layer_bootstrap.py."""

from __future__ import annotations

from app.ai_agents.general_agent.tools._tool_layer_bootstrap import (
    ToolLayer,
    _SERVER_TOOL_LAYERS,
)


class TestServerToolLayerRegistration:
    def test_x_search_tool_registered(self) -> None:
        assert _SERVER_TOOL_LAYERS.get("x_search_tool") == ToolLayer.EXTENDED

    def test_canvas_get_state_registered(self) -> None:
        assert _SERVER_TOOL_LAYERS.get("canvas_get_state") == ToolLayer.EXTENDED

    def test_canvas_get_selection_registered(self) -> None:
        assert _SERVER_TOOL_LAYERS.get("canvas_get_selection") == ToolLayer.EXTENDED

    def test_canvas_insert_element_registered(self) -> None:
        assert _SERVER_TOOL_LAYERS.get("canvas_insert_element") == ToolLayer.EXTENDED

    def test_canvas_batch_layout_registered(self) -> None:
        assert _SERVER_TOOL_LAYERS.get("canvas_batch_layout") == ToolLayer.EXTENDED

    def test_channel_notify_tool_registered(self) -> None:
        assert _SERVER_TOOL_LAYERS.get("channel_notify_tool") == ToolLayer.EXTENDED

    def test_media_tools_registered(self) -> None:
        for name in ("image_tool", "video_tool", "tts_generate"):
            assert _SERVER_TOOL_LAYERS.get(name) == ToolLayer.EXTENDED, name

    def test_browser_local_search_not_registered(self) -> None:
        assert "browser_local_search_tool" not in _SERVER_TOOL_LAYERS
