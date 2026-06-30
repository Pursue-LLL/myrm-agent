"""Tests for _setup_canvas_tools in tool_setup.py.

Verifies the guard conditions and lazy-loading behavior without
instantiating a full GeneralAgent (heavy dependencies).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.ai_agents.general_agent.tool_setup import ToolSetupMixin


def _make_stub(**attrs: object) -> ToolSetupMixin:
    """Build a minimal object that has ToolSetupMixin._setup_canvas_tools."""
    ns = SimpleNamespace(**attrs)
    ns._setup_canvas_tools = ToolSetupMixin._setup_canvas_tools.__get__(ns)
    return ns  # type: ignore[return-value]


class TestSetupCanvasToolsGuard:
    def test_skips_when_canvas_disabled(self) -> None:
        stub = _make_stub(enable_canvas=False, canvas_id="12345678-1234-1234-1234-123456789abc")
        deferred: list[object] = []
        stub._setup_canvas_tools(deferred)
        assert deferred == []

    def test_skips_when_canvas_id_none(self) -> None:
        stub = _make_stub(enable_canvas=True, canvas_id=None)
        deferred: list[object] = []
        stub._setup_canvas_tools(deferred)
        assert deferred == []

    def test_skips_when_both_missing(self) -> None:
        stub = _make_stub()
        deferred: list[object] = []
        stub._setup_canvas_tools(deferred)
        assert deferred == []

    def test_loads_tools_when_enabled_and_id_present(self) -> None:
        fake_tools = [MagicMock(name="t1"), MagicMock(name="t2"), MagicMock(name="t3")]
        stub = _make_stub(enable_canvas=True, canvas_id="12345678-1234-1234-1234-123456789abc")
        deferred: list[object] = []

        with patch(
            "app.services.canvas.canvas_agent_tools.create_canvas_tools",
            return_value=fake_tools,
        ):
            stub._setup_canvas_tools(deferred)

        assert len(deferred) == 3

    def test_degrades_gracefully_on_import_error(self) -> None:
        stub = _make_stub(enable_canvas=True, canvas_id="12345678-1234-1234-1234-123456789abc")
        deferred: list[object] = []

        with patch(
            "app.services.canvas.canvas_agent_tools.create_canvas_tools",
            side_effect=ImportError("no langchain"),
        ):
            stub._setup_canvas_tools(deferred)

        assert deferred == []
