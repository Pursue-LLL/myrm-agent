"""Doubles and builders for the MCP tool-table warm-up tests: a connection pool whose sessions a test holds back or fails.

[INPUT]
- myrm_agent_harness.toolkits.mcp.tool_converter::convert_mcp_tools (POS: builds the tool objects a live session exposes)
- myrm_agent_harness.toolkits.mcp.tool_table (POS: the table a surface is captured into)

[OUTPUT]
- FakePool / FakeConnection: pool double answering ``config_hash`` / ``is_pooled`` / ``get_connection`` for configured servers
- live_tools / table_of / config: the tools a live session exposes, the table captured from them, a stdio server config

[POS]
Harness pytest-only helper shared by the warm-up, routing and middleware tests, so each one states the servers it
serves and how their sessions behave, and not how a pool is faked.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence

from langchain_core.tools import BaseTool
from mcp.types import Tool

from myrm_agent_harness.toolkits.mcp.client import MCPServerConfigProtocol
from myrm_agent_harness.toolkits.mcp.config import MCPConfig
from myrm_agent_harness.toolkits.mcp.tool_converter import convert_mcp_tools
from myrm_agent_harness.toolkits.mcp.tool_table import ServerSurface, ToolTable, capture_table


async def _unused_call(name: str, arguments: dict[str, object]) -> object:
    raise AssertionError("a warm-up test never calls a tool")


def live_tools(*names: str, schema_chars: int = 0) -> list[BaseTool]:
    """Tools as a live session exposes them; ``schema_chars`` pads every description to weigh the schema down."""
    definitions = [
        Tool(
            name=name,
            description=f"{name} tool" + "x" * schema_chars,
            input_schema={"type": "object", "properties": {"q": {"type": "string"}}},
        )
        for name in names
    ]
    return list(convert_mcp_tools(definitions, _unused_call, server_name="demo"))


def table_of(*names: str, instructions: str | None = None, schema_chars: int = 0) -> ToolTable:
    table = capture_table(
        ServerSurface(tools=tuple(live_tools(*names, schema_chars=schema_chars)), instructions=instructions)
    )
    assert table is not None
    return table


def config(name: str = "demo") -> MCPConfig:
    return MCPConfig(name=name, type="stdio", command="echo")


class FakeConnection:
    """What a pooled connection exposes for one server."""

    def __init__(self, server: str, tools: list[BaseTool], instructions: str | None = None) -> None:
        self.tools_by_server = {server: tools}
        self.instructions_by_server = {server: instructions}


class FakePool:
    """Connection pool double: which servers are pooled, what a connection exposes, and whether it comes up."""

    def __init__(self) -> None:
        self.pooled: set[str] = set()
        self.live: dict[str, FakeConnection] = {}
        self.failure: Exception | None = None
        self.gate: asyncio.Event | None = None
        self.asked: list[str] = []

    def config_hash(self, configs: Sequence[MCPServerConfigProtocol]) -> str:
        return f"hash-{configs[0].name}"

    def is_pooled(self, configs: Sequence[MCPServerConfigProtocol]) -> bool:
        return configs[0].name in self.pooled

    async def get_connection(self, configs: Sequence[MCPServerConfigProtocol]) -> FakeConnection:
        """Wait for ``gate`` when one is set, then fail with ``failure`` or hand out the server's connection."""
        name = configs[0].name
        self.asked.append(name)
        if self.gate is not None:
            await self.gate.wait()
        if self.failure is not None:
            raise self.failure
        if name not in self.live:
            raise ConnectionError(f"no server named {name}")
        self.pooled.add(name)
        return self.live[name]
