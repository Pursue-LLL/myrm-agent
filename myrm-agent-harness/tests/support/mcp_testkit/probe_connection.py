"""The annotations probe server seen through the production connection pool.

[INPUT]
- myrm_agent_harness.toolkits.mcp.connection_manager::MCPConnectionManager (POS: warm connection pool; the path a session takes)
- myrm_agent_harness.toolkits.mcp.config::MCPConfig (POS: MCP server configuration)
- myrm_agent_harness.toolkits.mcp.tool_processing::register_tool_annotations (POS: the registration step the pool runs on every tool list)
- myrm_agent_harness.core.security.tool_registry::get_ptc_safety_metadata, register_ptc_safety_metadata (POS: what that registration recorded, and the loosest record a consumer could ever meet)
- tests.support.mcp_testkit.annotations_probe_server::build_annotations_probe_server (POS: the probe server)
- tests.support.mcp_testkit.live_server::start_live_server, HTTP_ENDPOINT_PATH (POS: loopback HTTP hosting)

[OUTPUT]
- SERVER_NAME: the name the probe server is configured under
- ProbeServer: the tools the pool hands to a session, by the name the server declares them under, and the safety records registered for them (the judged ones, or the loosest ones)
- connect_probe_server: connect over stdio or streamable HTTP and yield the ProbeServer

[POS]
Harness pytest-only helper shared by the MCP annotations tests, so each of them runs the real server, converter,
processing chain and registration instead of a hand-built tool.
"""

from __future__ import annotations

import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from langchain_core.tools import BaseTool

from myrm_agent_harness.core.security.tool_registry import (
    MCPAnnotations,
    SafetyMetadata,
    get_ptc_safety_metadata,
    register_ptc_safety_metadata,
)
from myrm_agent_harness.toolkits.mcp.config import MCPConfig
from myrm_agent_harness.toolkits.mcp.connection_manager import MCPConnectionManager
from myrm_agent_harness.toolkits.mcp.tool_processing import register_tool_annotations
from tests.support.mcp_testkit.annotations_probe_server import build_annotations_probe_server
from tests.support.mcp_testkit.live_server import HTTP_ENDPOINT_PATH, LiveServer, start_live_server

SERVER_NAME = "probe"

_SERVER_SCRIPT = Path(__file__).with_name("annotations_probe_server.py")
_CALL_PREFIX = f"mcp__{SERVER_NAME}__"


@dataclass(frozen=True, slots=True)
class ProbeServer:
    """What a session receives from the probe server: processed tools keyed by the name the server declares."""

    marks_dir: Path
    host_serial: bool
    tools: dict[str, BaseTool]

    @property
    def skill_name(self) -> str:
        return f"mcp_{SERVER_NAME}_skill"

    def call_name(self, declared_name: str) -> str:
        """The name the model calls the tool by."""
        return f"{_CALL_PREFIX}{declared_name}"

    def registered(self) -> dict[str, tuple[SafetyMetadata, MCPAnnotations]]:
        """The safety record and claim slot the registry holds for each tool right now."""
        entries = {name: get_ptc_safety_metadata(self.skill_name, tool.name) for name, tool in self.tools.items()}
        return {name: entry for name, entry in entries.items() if entry is not None}

    def register(self) -> None:
        """Run the pool's registration step again; ``tests/conftest.py`` empties the registry between tests."""
        register_tool_annotations(list(self.tools.values()), SERVER_NAME, self.host_serial)

    def register_loosest(self) -> None:
        """Overwrite every tool's record with the loosest one, under both spellings of its name.

        This is what a consumer would face if the hand-off from a server's claims ever stopped judging: the
        records a claim can never produce, filed where each consumer looks (the declared name a script uses and
        the prefixed name the model calls).
        """
        loosest = SafetyMetadata(is_read_only=True, is_concurrent_safe=True, is_idempotent=True)
        for name in self.tools:
            for spelling in (name, self.call_name(name)):
                register_ptc_safety_metadata(self.skill_name, spelling, loosest, {})


@asynccontextmanager
async def connect_probe_server(
    transport: Literal["stdio", "streamable_http"],
    marks_dir: Path,
    *,
    host_serial: bool = False,
) -> AsyncIterator[ProbeServer]:
    manager = MCPConnectionManager()
    await manager.start()
    live: LiveServer | None = None
    try:
        common = {
            "name": SERVER_NAME,
            "description": "annotations probe",
            "connect_timeout": 30.0,
            "host_serial": host_serial,
        }
        if transport == "stdio":
            config = MCPConfig(
                type="stdio", command=sys.executable, args=[str(_SERVER_SCRIPT), str(marks_dir)], **common
            )
        else:
            live = await start_live_server(build_annotations_probe_server(marks_dir).streamable_http_app())
            config = MCPConfig(type="streamable_http", url=f"{live.base_url}{HTTP_ENDPOINT_PATH[transport]}", **common)
        connection = await manager.get_connection([config])
        tools = {tool.name.removeprefix(_CALL_PREFIX): tool for tool in connection.tools_by_server[SERVER_NAME]}
        yield ProbeServer(marks_dir=marks_dir, host_serial=host_serial, tools=tools)
    finally:
        await manager.stop()
        if live is not None:
            await live.stop()
