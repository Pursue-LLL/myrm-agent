"""A serializable snapshot of the tools one MCP server exposes.

[INPUT]
- toolkits.mcp.structured_tool::SafeStructuredTool (POS: StructuredTool whose callable receives every argument)

[OUTPUT]
- ServerSurface: The tools and handshake instructions the Skill surface of one server is generated from
- ToolTable: JSON-serializable snapshot of a ServerSurface
- tools_of_server: The tools a pooled connection holds for one configured server
- capture_table, restore_surface: ServerSurface <-> ToolTable
- encode_table, decode_table: ToolTable <-> JSON text

[POS]
Everything the L1 description, the L2 index and the L3 documents of an MCP Skill read from a live session, in a form
that outlives the process. Restoring a captured table yields tools the Skill generator treats exactly like the tools of
a live session, so the surface can be built before the session is up.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from langchain_core.tools import BaseTool

from myrm_agent_harness.toolkits.mcp.structured_tool import SafeStructuredTool

_FORMAT_VERSION = 1
"""Bumped when the payload layout changes, so a table written by another layout reads as absent."""

_OUTPUT_SCHEMA_KEY = "mcp_output_schema"
"""Tool metadata key the Skill generator reads a tool's output schema from."""

type JsonObject = dict[str, object]


@dataclass(frozen=True, slots=True)
class ServerSurface:
    """The part of a live MCP session that the Skill surface of its server is generated from."""

    tools: tuple[BaseTool, ...]
    instructions: str | None


@dataclass(frozen=True, slots=True)
class TableTool:
    """One tool as the Skill generator reads it."""

    name: str
    description: str
    args_schema: JsonObject
    output_schema: JsonObject | None


@dataclass(frozen=True, slots=True)
class ToolTable:
    """JSON-serializable snapshot of a ``ServerSurface``."""

    tools: tuple[TableTool, ...]
    instructions: str | None


def tools_of_server(tools_by_server: Mapping[str, Sequence[BaseTool]], server_name: str) -> list[BaseTool]:
    """Tools a pooled connection holds for *server_name*.

    Falls back to the connection's first populated entry when the configured name is not a key.
    """
    return list(tools_by_server.get(server_name) or next((tools for tools in tools_by_server.values() if tools), []))


def capture_table(surface: ServerSurface) -> ToolTable | None:
    """Snapshot *surface*, or ``None`` when it holds something a table cannot carry.

    The snapshot is normalized through JSON, so it equals the table read back from disk and two captures of the same
    surface encode to the same text.
    """
    tools: list[TableTool] = []
    for tool in surface.tools:
        if not isinstance(tool.args_schema, dict):
            return None
        output_schema = (tool.metadata or {}).get(_OUTPUT_SCHEMA_KEY)
        tools.append(
            TableTool(
                name=tool.name,
                description=tool.description or "",
                args_schema=tool.args_schema,
                output_schema=output_schema if isinstance(output_schema, dict) and output_schema else None,
            )
        )
    try:
        return decode_table(encode_table(ToolTable(tools=tuple(tools), instructions=surface.instructions)))
    except (TypeError, ValueError):
        return None


async def _describe_only(**_arguments: object) -> object:
    raise RuntimeError("A restored MCP tool only describes the tool; it cannot run it")


def restore_surface(table: ToolTable) -> ServerSurface:
    """Rebuild the surface *table* was captured from, with tools that describe but cannot run.

    Schemas are copied so nothing downstream can alter the table the surface came from.
    """
    tools = tuple(
        SafeStructuredTool(
            name=tool.name,
            description=tool.description,
            args_schema=copy.deepcopy(tool.args_schema),
            coroutine=_describe_only,
            metadata={_OUTPUT_SCHEMA_KEY: copy.deepcopy(tool.output_schema)} if tool.output_schema else {},
        )
        for tool in table.tools
    )
    return ServerSurface(tools=tools, instructions=table.instructions)


def encode_table(table: ToolTable) -> str:
    """JSON text of *table*; key order is kept, because the order the model reads the schemas in is part of the table."""
    return json.dumps(
        {
            "version": _FORMAT_VERSION,
            "instructions": table.instructions,
            "tools": [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "args_schema": tool.args_schema,
                    "output_schema": tool.output_schema,
                }
                for tool in table.tools
            ],
        },
        ensure_ascii=False,
        allow_nan=False,
    )


def decode_table(text: str) -> ToolTable | None:
    """The table *text* encodes, or ``None`` when it is not a table of this layout."""
    try:
        payload = json.loads(text)
    except (ValueError, RecursionError):
        return None
    if not isinstance(payload, dict) or payload.get("version") != _FORMAT_VERSION:
        return None
    instructions = payload.get("instructions")
    raw_tools = payload.get("tools")
    if not (instructions is None or isinstance(instructions, str)) or not isinstance(raw_tools, list) or not raw_tools:
        return None
    tools: list[TableTool] = []
    for raw in raw_tools:
        if not isinstance(raw, dict):
            return None
        name, description = raw.get("name"), raw.get("description")
        args_schema, output_schema = raw.get("args_schema"), raw.get("output_schema")
        if not (
            isinstance(name, str)
            and isinstance(description, str)
            and isinstance(args_schema, dict)
            and (output_schema is None or isinstance(output_schema, dict))
        ):
            return None
        tools.append(
            TableTool(name=name, description=description, args_schema=args_schema, output_schema=output_schema)
        )
    return ToolTable(tools=tuple(tools), instructions=instructions)


__all__ = [
    "ServerSurface",
    "TableTool",
    "ToolTable",
    "capture_table",
    "decode_table",
    "encode_table",
    "restore_surface",
    "tools_of_server",
]
