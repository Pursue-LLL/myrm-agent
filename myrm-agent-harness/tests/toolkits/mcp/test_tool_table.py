"""Tool tables: a captured surface restores into tools the Skill generator cannot tell from the live ones.

[INPUT]
- myrm_agent_harness.toolkits.mcp.tool_table (POS: unit under test)
- myrm_agent_harness.toolkits.mcp.tool_converter::convert_mcp_tools (POS: builds the live tool objects)

[OUTPUT]
- Unit tests for capture, restore, JSON encoding and decoding of tool tables, and for the tool lookup of a connection.
"""

from __future__ import annotations

import json

import pytest
from langchain_core.tools import BaseTool
from mcp.types import Tool
from pydantic import BaseModel

from myrm_agent_harness.toolkits.mcp.structured_tool import SafeStructuredTool
from myrm_agent_harness.toolkits.mcp.tool_converter import convert_mcp_tools
from myrm_agent_harness.toolkits.mcp.tool_table import (
    ServerSurface,
    ToolTable,
    capture_table,
    decode_table,
    encode_table,
    restore_surface,
    tools_of_server,
)


async def _unused_call(name: str, arguments: dict[str, object]) -> object:
    raise AssertionError("a surface test never calls a tool")


def _live_tools() -> tuple[BaseTool, ...]:
    """Tools as a live session exposes them: converted from the server's MCP tool definitions."""
    definitions = [
        Tool(
            name="mcp__demo__search",
            description="Search the index. Returns matching documents.",
            input_schema={
                "type": "object",
                "properties": {"query": {"type": "string", "description": "Search text"}, "limit": {"type": "integer"}},
                "required": ["query"],
            },
            output_schema={"type": "object", "properties": {"hits": {"type": "array"}}},
        ),
        Tool(name="mcp__demo__ping", description="", input_schema={"type": "object", "properties": {}}),
    ]
    return tuple(convert_mcp_tools(definitions, _unused_call, server_name="demo"))


def _table(surface: ServerSurface) -> ToolTable:
    table = capture_table(surface)
    assert table is not None
    return table


def test_capture_then_restore_keeps_every_field_the_generator_reads() -> None:
    live = ServerSurface(tools=_live_tools(), instructions="Use search first.")

    restored = restore_surface(_table(live))

    assert restored.instructions == "Use search first."
    assert [tool.name for tool in restored.tools] == [tool.name for tool in live.tools]
    for before, after in zip(live.tools, restored.tools, strict=True):
        assert after.description == before.description
        assert after.args_schema == before.args_schema
        assert (after.metadata or {}) == (before.metadata or {})
    assert isinstance(restored.tools[0], SafeStructuredTool)


def test_encoding_keeps_key_order_and_two_captures_encode_alike() -> None:
    live = ServerSurface(tools=_live_tools(), instructions=None)

    first, second = _table(live), _table(live)

    assert encode_table(first) == encode_table(second)
    decoded = decode_table(encode_table(first))
    assert decoded is not None
    assert encode_table(decoded) == encode_table(first)
    properties = first.tools[0].args_schema["properties"]
    assert isinstance(properties, dict)
    assert list(properties) == ["query", "limit"]


def test_capture_normalizes_through_json() -> None:
    tool = SafeStructuredTool(
        name="t",
        description="d",
        args_schema={"type": "object", "enum": ("a", "b"), "properties": {}},
        coroutine=_unused_call,
    )

    table = _table(ServerSurface(tools=(tool,), instructions=None))

    assert table.tools[0].args_schema["enum"] == ["a", "b"]


@pytest.mark.parametrize(
    "surface",
    [
        ServerSurface(tools=(), instructions=None),
        ServerSurface(
            tools=(
                SafeStructuredTool(
                    name="t",
                    description="d",
                    args_schema={"type": "object", "properties": {"x": {"default": {1, 2}}}},
                    coroutine=_unused_call,
                ),
            ),
            instructions=None,
        ),
    ],
    ids=["no-tools", "schema-not-json"],
)
def test_capture_declines_what_a_table_cannot_carry(surface: ServerSurface) -> None:
    assert capture_table(surface) is None


def test_capture_declines_a_tool_whose_schema_is_a_model_class() -> None:
    class _Args(BaseModel):
        value: str

    tool = SafeStructuredTool(name="t", description="d", args_schema=_Args, coroutine=_unused_call)

    assert capture_table(ServerSurface(tools=(tool,), instructions=None)) is None


def test_restore_copies_schemas_so_the_table_stays_intact() -> None:
    table = _table(ServerSurface(tools=_live_tools(), instructions=None))
    before = encode_table(table)

    restored = restore_surface(table)
    schema = restored.tools[0].args_schema
    assert isinstance(schema, dict)
    schema["properties"]["query"]["description"] = "changed"
    output_schema = (restored.tools[0].metadata or {})["mcp_output_schema"]
    output_schema["properties"].clear()

    assert encode_table(table) == before


async def test_a_restored_tool_describes_but_cannot_run() -> None:
    restored = restore_surface(_table(ServerSurface(tools=_live_tools(), instructions=None)))

    with pytest.raises(RuntimeError, match="only describes the tool"):
        await restored.tools[0].ainvoke({"query": "x"})


@pytest.mark.parametrize(
    "text",
    [
        "not json",
        "[]",
        json.dumps({"version": 999, "instructions": None, "tools": [{}]}),
        json.dumps({"version": 1, "instructions": None, "tools": []}),
        json.dumps({"version": 1, "instructions": 5, "tools": [{"name": "t"}]}),
        json.dumps({"version": 1, "instructions": None, "tools": "nope"}),
        json.dumps({"version": 1, "instructions": None, "tools": ["nope"]}),
        json.dumps(
            {
                "version": 1,
                "instructions": None,
                "tools": [{"name": 1, "description": "d", "args_schema": {}, "output_schema": None}],
            }
        ),
        json.dumps(
            {
                "version": 1,
                "instructions": None,
                "tools": [{"name": "t", "description": "d", "args_schema": [], "output_schema": None}],
            }
        ),
        json.dumps(
            {
                "version": 1,
                "instructions": None,
                "tools": [{"name": "t", "description": "d", "args_schema": {}, "output_schema": "x"}],
            }
        ),
        "[" * 100_000,
    ],
    ids=[
        "invalid-json",
        "not-an-object",
        "other-version",
        "no-tools",
        "bad-instructions",
        "tools-not-a-list",
        "tool-not-an-object",
        "bad-name",
        "bad-schema",
        "bad-output-schema",
        "too-deep",
    ],
)
def test_decode_reads_anything_but_a_table_as_absent(text: str) -> None:
    assert decode_table(text) is None


def test_tools_of_server_prefers_the_configured_name() -> None:
    tools = list(_live_tools())

    assert tools_of_server({"demo": tools, "other": tools[:1]}, "demo") == tools


def test_tools_of_server_falls_back_to_the_first_populated_entry() -> None:
    tools = list(_live_tools())

    assert tools_of_server({"empty": [], "announced": tools}, "configured") == tools
    assert tools_of_server({"empty": []}, "configured") == []


def test_tools_of_server_returns_a_copy() -> None:
    held = list(_live_tools())

    returned = tools_of_server({"demo": held}, "demo")
    returned.clear()

    assert len(held) == 2
