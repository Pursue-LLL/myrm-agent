"""Tests for shrinking oversized tool-call arguments during fallback compaction."""

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from myrm_agent_harness.agent.context_management.strategies.compactor.smart_fallback import apply_smart_fallback
from myrm_agent_harness.agent.context_management.strategies.compression.compression_formatting import (
    _shrink_value,
    shrink_tool_call_args,
)


class TestShrinkToolCallArgs:
    """Tests for shrink_tool_call_args and _shrink_value."""

    def test_short_string_unchanged(self) -> None:
        result = _shrink_value("short text")
        assert result == "short text"

    def test_long_string_truncated(self) -> None:
        long_str = "x" * 1000
        result = _shrink_value(long_str)
        assert isinstance(result, str)
        assert len(result) < 1000
        assert "chars omitted" in result
        assert result.startswith("x" * 200)
        assert result.endswith("x" * 50)

    def test_nested_dict_values_shrunk(self) -> None:
        data = {"key": "a" * 1000, "short": "ok", "num": 42}
        result = _shrink_value(data)
        assert isinstance(result, dict)
        assert "chars omitted" in result["key"]
        assert result["short"] == "ok"
        assert result["num"] == 42

    def test_list_values_shrunk(self) -> None:
        data = ["a" * 1000, "short"]
        result = _shrink_value(data)
        assert isinstance(result, list)
        assert len(result) == 2
        assert "chars omitted" in result[0]
        assert result[1] == "short"

    def test_long_list_capped(self) -> None:
        data = list(range(30))
        result = _shrink_value(data)
        assert isinstance(result, list)
        assert len(result) == 11
        assert "20 more items omitted" in result[-1]

    def test_shrink_tool_call_args_preserves_structure(self) -> None:
        tool_calls = [
            {"name": "file_write", "args": {"path": "/tmp/test.py", "content": "x" * 2000}, "id": "c1"},
            {"name": "search", "args": {"query": "short"}, "id": "c2"},
        ]
        result = shrink_tool_call_args(tool_calls)
        assert len(result) == 2
        write_args, search_args = result[0]["args"], result[1]["args"]
        assert isinstance(write_args, dict)
        assert isinstance(search_args, dict)
        assert result[0]["name"] == "file_write"
        assert result[0]["id"] == "c1"
        assert "chars omitted" in write_args["content"]
        assert write_args["path"] == "/tmp/test.py"
        assert search_args["query"] == "short"

    def test_shrink_does_not_mutate_original(self) -> None:
        original_content = "y" * 1000
        args = {"data": original_content}
        tool_calls = [{"name": "tool", "args": args, "id": "c1"}]
        shrink_tool_call_args(tool_calls)
        assert args["data"] == original_content

    def test_shrink_with_non_dict_args(self) -> None:
        tool_calls = [{"name": "tool", "args": "not_a_dict", "id": "c1"}]
        result = shrink_tool_call_args(tool_calls)
        assert result[0]["args"] == "not_a_dict"

    @pytest.mark.parametrize("args", ["not_a_dict", {"query": "short"}], ids=["opaque-args", "dict-args"])
    def test_every_returned_call_is_a_copy_the_caller_may_edit(self, args: object) -> None:
        call: dict[str, object] = {"name": "tool", "args": args, "id": "c1"}

        (copied,) = shrink_tool_call_args([call])
        copied["id"] = "edited"

        assert call["id"] == "c1"

    def test_shrink_empty_tool_calls(self) -> None:
        assert shrink_tool_call_args([]) == []

    @pytest.mark.asyncio
    async def test_truncate_ai_message_shrinks_tool_call_args(self) -> None:
        """_truncate_ai_message should shrink tool_call args with long content."""
        messages = [
            HumanMessage(content="Q"),
            AIMessage(
                content="Calling file_write",
                tool_calls=[
                    {
                        "name": "file_write",
                        "args": {"path": "/test.py", "content": "z" * 2000},
                        "id": "c1",
                    }
                ],
            ),
            ToolMessage(content="Success", tool_call_id="c1"),
            AIMessage(content="Done"),
        ]

        fallback_messages, _ = await apply_smart_fallback(messages, max_tokens=1500)

        ai_with_calls = [m for m in fallback_messages if isinstance(m, AIMessage) and m.tool_calls]
        assert ai_with_calls, "the tool call must survive the fallback for its arguments to be shrunk"
        args = ai_with_calls[0].tool_calls[0]["args"]
        assert "chars omitted" in args["content"]
        assert args["path"] == "/test.py"
