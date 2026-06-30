"""Tests for canvas tool layer registration in _tool_layer_bootstrap.py.

Verifies canvas tools are registered as EXTENDED layer.
"""

from __future__ import annotations

from app.ai_agents.general_agent.tools._tool_layer_bootstrap import (
    ToolLayer,
    _SERVER_TOOL_LAYERS,
)


class TestCanvasToolLayerRegistration:
    def test_canvas_get_state_registered(self) -> None:
        assert _SERVER_TOOL_LAYERS.get("canvas_get_state") == ToolLayer.EXTENDED

    def test_canvas_get_selection_registered(self) -> None:
        assert _SERVER_TOOL_LAYERS.get("canvas_get_selection") == ToolLayer.EXTENDED

    def test_canvas_insert_element_registered(self) -> None:
        assert _SERVER_TOOL_LAYERS.get("canvas_insert_element") == ToolLayer.EXTENDED
