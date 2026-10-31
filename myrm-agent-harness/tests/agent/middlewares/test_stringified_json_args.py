"""stringified_json_args_middleware: JSON strings sent for list and object fields reach the tool parsed.

The end-to-end behaviour on the shipped graph is pinned in ``test_shipped_stack_tool_dispatch``; these tests pin the
rules that decide what is parsed: which fields, which strings, and that nothing outside the copy handed on changes.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from langchain.agents.middleware import ToolCallRequest
from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool, StructuredTool, tool
from pydantic import BaseModel

from myrm_agent_harness.agent.middlewares.tooling.stringified_json_args import stringified_json_args_middleware


@tool
def sample(items: list[str], filters: dict[str, str], note: str, maybe_items: list[str] | None = None) -> str:
    """Take one of every kind of field."""
    return "ok"


def _request(args: object, target: BaseTool | None = sample) -> ToolCallRequest:
    return ToolCallRequest(
        tool_call={"name": "sample", "id": "call-1", "args": args, "type": "tool_call"},  # type: ignore[typeddict-item]
        tool=target,
        state={"messages": []},
        runtime=MagicMock(),
    )


async def _run(request: ToolCallRequest) -> ToolCallRequest:
    """The request the tool is run with."""
    seen: list[ToolCallRequest] = []

    async def handler(handed_on: ToolCallRequest) -> ToolMessage:
        seen.append(handed_on)
        return ToolMessage(content="ok", tool_call_id="call-1")

    await stringified_json_args_middleware.awrap_tool_call(request, handler)
    return seen[0]


async def test_a_json_string_for_a_list_field_is_parsed() -> None:
    handed_on = await _run(_request({"items": '["a", "b"]', "filters": {}, "note": "n"}))

    assert handed_on.tool_call["args"]["items"] == ["a", "b"]


async def test_a_json_string_for_an_object_field_is_parsed() -> None:
    handed_on = await _run(_request({"items": [], "filters": '{"status": "open"}', "note": "n"}))

    assert handed_on.tool_call["args"]["filters"] == {"status": "open"}


async def test_an_optional_list_field_is_parsed_too() -> None:
    handed_on = await _run(_request({"items": [], "filters": {}, "note": "n", "maybe_items": '["x"]'}))

    assert handed_on.tool_call["args"]["maybe_items"] == ["x"]


async def test_a_truncated_object_string_is_repaired_once() -> None:
    handed_on = await _run(_request({"items": [], "filters": '{"status": "open", "kind": "fil', "note": "n"}))

    assert handed_on.tool_call["args"]["filters"] == {"status": "open", "kind": "fil"}


async def test_a_string_that_cannot_be_repaired_stays_a_string() -> None:
    request = _request({"items": [], "filters": '{"status": ', "note": "n"})

    handed_on = await _run(request)

    assert handed_on is request


async def test_a_string_field_that_looks_like_a_list_is_left_alone() -> None:
    request = _request({"items": [], "filters": {}, "note": "[not a list]"})

    handed_on = await _run(request)

    assert handed_on is request


async def test_a_list_field_string_that_is_not_valid_json_is_left_alone() -> None:
    request = _request({"items": "[1]x", "filters": {}, "note": "n"})

    handed_on = await _run(request)

    assert handed_on is request


async def test_the_arguments_on_the_models_message_are_not_changed() -> None:
    sent = {"items": '["a"]', "filters": {}, "note": "n"}
    request = _request(sent)

    handed_on = await _run(request)

    assert handed_on is not request
    assert request.tool_call["args"] == {"items": '["a"]', "filters": {}, "note": "n"}
    assert sent["items"] == '["a"]'


async def test_values_that_are_already_native_pass_through_untouched() -> None:
    request = _request({"items": ["a"], "filters": {"k": "v"}, "note": "n"})

    assert await _run(request) is request


@pytest.mark.parametrize("args", [None, "not a dict", ["a list"]])
async def test_arguments_that_are_not_a_mapping_pass_through(args: object) -> None:
    request = _request(args)

    assert await _run(request) is request


async def test_a_call_without_a_resolved_tool_passes_through() -> None:
    request = _request({"items": '["a"]'}, target=None)

    assert await _run(request) is request


async def test_a_tool_with_a_json_schema_dict_passes_through() -> None:
    """Such a tool (an MCP tool) parses its own arguments against that schema."""
    dict_schema_tool = StructuredTool(
        name="sample",
        description="Takes a list.",
        args_schema={"type": "object", "properties": {"items": {"type": "array"}}},
        coroutine=MagicMock(),
    )
    request = _request({"items": '["a"]'}, target=dict_schema_tool)

    assert await _run(request) is request


async def test_schema_classes_with_the_same_name_do_not_share_their_fields() -> None:
    def make(field_annotation: object) -> type[BaseModel]:
        return type("Input", (BaseModel,), {"__annotations__": {"value": field_annotation}})

    def tool_of(schema: type[BaseModel]) -> BaseTool:
        return StructuredTool(name="sample", description="d", args_schema=schema, coroutine=MagicMock())

    as_list = tool_of(make(list[str]))
    as_text = tool_of(make(str))

    assert (await _run(_request({"value": '["a"]'}, target=as_list))).tool_call["args"]["value"] == ["a"]
    assert (await _run(_request({"value": '["a"]'}, target=as_text))).tool_call["args"]["value"] == '["a"]'
