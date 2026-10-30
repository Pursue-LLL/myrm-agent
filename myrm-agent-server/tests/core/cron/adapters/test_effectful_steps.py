"""Which recorded steps count as "this run already did something a repeat would do again"."""

from __future__ import annotations

import pytest

from app.core.cron.adapters.effectful_steps import has_effectful_tools


@pytest.mark.parametrize("tool_name", ["file_write_tool", "browser_navigate_tool", "send_message", "execute_command"])
def test_a_state_changing_tool_is_effectful(tool_name: str) -> None:
    assert has_effectful_tools([{"tool_name": "web_search_tool"}, {"tool_name": tool_name}]) is True


def test_read_only_tools_are_not_effectful() -> None:
    steps: list[dict[str, object]] = [
        {"tool_name": "file_read_tool"},
        {"tool_name": "grep_tool"},
        {"tool_name": "web_fetch_tool"},
    ]

    assert has_effectful_tools(steps) is False


def test_an_unregistered_tool_counts_as_effectful() -> None:
    """A side effect must never go unnoticed because nobody classified the tool."""
    assert has_effectful_tools([{"tool_name": "tool_nobody_registered"}]) is True


@pytest.mark.parametrize("tool_name", [None, 7])
def test_steps_without_a_tool_name_are_not_tool_calls(tool_name: object) -> None:
    assert has_effectful_tools([{"step_key": "reviewing_sources", "tool_name": tool_name}, {"step_key": "plan"}]) is False


def test_no_steps_is_not_effectful() -> None:
    assert has_effectful_tools([]) is False
