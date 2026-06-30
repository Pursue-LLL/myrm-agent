"""Tests for canvas-related changes in profile_resolver.

Covers: BuiltinToolFlags.enable_canvas, resolve_builtin_tool_flags canvas mapping.
"""

from __future__ import annotations

from app.services.agent.profile_resolver import BuiltinToolFlags, resolve_builtin_tool_flags


class TestResolveBuiltinToolFlagsCanvas:
    def test_canvas_enabled_when_present(self) -> None:
        flags = resolve_builtin_tool_flags(["web_search", "memory", "canvas"])
        assert flags["enable_canvas"] is True

    def test_canvas_disabled_when_absent(self) -> None:
        flags = resolve_builtin_tool_flags(["web_search", "memory"])
        assert flags["enable_canvas"] is False

    def test_canvas_only(self) -> None:
        flags = resolve_builtin_tool_flags(["canvas"])
        assert flags["enable_canvas"] is True
        assert flags["enable_browser"] is False

    def test_all_tools_enabled(self) -> None:
        all_tools = [
            "browser", "computer_use", "file_ops", "code_execute",
            "wiki", "kanban", "canvas", "llm_map", "answer_tool", "render_ui",
        ]
        flags = resolve_builtin_tool_flags(all_tools)
        for key in BuiltinToolFlags.__annotations__:
            assert flags[key] is True, f"{key} should be True"  # type: ignore[literal-required]

    def test_empty_list_all_disabled(self) -> None:
        flags = resolve_builtin_tool_flags([])
        for key in BuiltinToolFlags.__annotations__:
            assert flags[key] is False, f"{key} should be False"  # type: ignore[literal-required]
