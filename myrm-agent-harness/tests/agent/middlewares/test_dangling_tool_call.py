"""Tests for middlewares.dangling_tool_call_middleware — repair dangling tool_calls."""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from myrm_agent_harness.agent.middlewares.tooling.dangling_tool_call_middleware import (
    _INTERRUPTED_MUTATION_CONTENT,
    _build_patched_messages,
)
from myrm_agent_harness.agent.tool_management.tool_layers import get_tool_replay_safety
from myrm_agent_harness.agent.tool_management.types import ReplaySafety


class TestBuildPatchedMessages:
    def test_no_dangling_returns_none(self) -> None:
        messages = [
            HumanMessage(content="hi"),
            AIMessage(content="", tool_calls=[{"id": "tc1", "name": "tool", "args": {}}]),
            ToolMessage(content="result", tool_call_id="tc1"),
        ]
        assert _build_patched_messages(messages) is None

    def test_no_tool_calls_returns_none(self) -> None:
        messages = [
            HumanMessage(content="hi"),
            AIMessage(content="hello"),
        ]
        assert _build_patched_messages(messages) is None

    def test_patches_dangling_tool_call(self) -> None:
        messages = [
            HumanMessage(content="hi"),
            AIMessage(
                content="",
                tool_calls=[{"id": "tc1", "name": "bash_code_execute_tool", "args": {}}],
            ),
        ]
        patched = _build_patched_messages(messages)
        assert patched is not None
        assert len(patched) == 3
        synthetic = patched[2]
        assert isinstance(synthetic, ToolMessage)
        assert synthetic.tool_call_id == "tc1"
        assert synthetic.content == _INTERRUPTED_MUTATION_CONTENT

    def test_desktop_vision_tool_is_not_replay_safe(self) -> None:
        """Vision actions click, type and press keys, so only the read-only snapshot may be replayed."""
        assert get_tool_replay_safety("desktop_vision_tool") is ReplaySafety.NEVER
        assert get_tool_replay_safety("desktop_snapshot_tool") is ReplaySafety.SAFE

    def test_interrupted_desktop_vision_call_is_reported_as_side_effecting(self) -> None:
        messages = [
            HumanMessage(content="click save"),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "id": "tc1",
                        "name": "desktop_vision_tool",
                        "args": {"action": "left_click", "coordinate": [10, 20]},
                    }
                ],
            ),
        ]
        patched = _build_patched_messages(messages)
        assert patched is not None
        synthetic = patched[-1]
        assert isinstance(synthetic, ToolMessage)
        assert synthetic.content == _INTERRUPTED_MUTATION_CONTENT
        assert synthetic.status == "error"

    def test_patches_multiple_dangling(self) -> None:
        messages = [
            HumanMessage(content="hi"),
            AIMessage(
                content="",
                tool_calls=[
                    {"id": "tc1", "name": "tool_a", "args": {}},
                    {"id": "tc2", "name": "tool_b", "args": {}},
                ],
            ),
        ]
        patched = _build_patched_messages(messages)
        assert patched is not None
        tool_msgs = [m for m in patched if isinstance(m, ToolMessage)]
        assert len(tool_msgs) == 2

    def test_mixed_dangling_and_resolved(self) -> None:
        messages = [
            HumanMessage(content="hi"),
            AIMessage(
                content="",
                tool_calls=[
                    {"id": "tc1", "name": "tool_a", "args": {}},
                    {"id": "tc2", "name": "tool_b", "args": {}},
                ],
            ),
            ToolMessage(content="result", tool_call_id="tc1"),
        ]
        patched = _build_patched_messages(messages)
        assert patched is not None
        synthetic_msgs = [
            m for m in patched if isinstance(m, ToolMessage) and m.content == _INTERRUPTED_MUTATION_CONTENT
        ]
        assert len(synthetic_msgs) == 1
        assert synthetic_msgs[0].tool_call_id == "tc2"

    def test_empty_messages(self) -> None:
        assert _build_patched_messages([]) is None

    def test_no_id_in_tool_call_sanitized(self) -> None:
        """Tool calls without id are sanitized (removed), returning a cleaned message list."""
        ai_msg = AIMessage(content="")
        ai_msg.tool_calls = [{"name": "tool", "args": {}}]  # type: ignore[list-item]
        messages = [ai_msg]
        patched = _build_patched_messages(messages)
        assert patched is not None
        assert len(patched) == 1
        assert isinstance(patched[0], AIMessage)
        assert patched[0].tool_calls == []
