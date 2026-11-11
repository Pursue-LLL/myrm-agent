"""The two surfaces an agent manages an existing memory through.

[INPUT]
- toolkits.memory.agent_surface.mcp_server::MemoryMCPServer (POS: MCP adapter exposing memory_manage)
- toolkits.memory.agent_surface.memory_agent_tools.manage_tool::build_memory_manage_tool (POS: in-process memory_manage_tool)
- toolkits.memory.manager::MemoryManager (POS: memory lifecycle manager)

[OUTPUT]
- Manage / ManageArguments: one manage call over a surface, and the arguments it takes
- manage_with_agent_tool: manage through the in-process ``memory_manage_tool``
- manage_with_mcp_tool: manage through the MCP ``memory_manage`` tool
- MANAGES: both surfaces as pytest params

[POS]
Harness pytest-only driver shared by the manage-tool tests, so a test states the arguments it manages with and runs
unchanged over both surfaces.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping

import pytest

from myrm_agent_harness.toolkits.memory.agent_surface.mcp_server import MemoryMCPServer
from myrm_agent_harness.toolkits.memory.agent_surface.memory_agent_tools.manage_tool import build_memory_manage_tool
from myrm_agent_harness.toolkits.memory.manager import MemoryManager

type ManageArguments = Mapping[str, str | float]
type Manage = Callable[[MemoryManager, ManageArguments], Awaitable[str]]


async def manage_with_agent_tool(manager: MemoryManager, arguments: ManageArguments) -> str:
    reply = await build_memory_manage_tool(manager, description="manage").ainvoke(dict(arguments))
    assert isinstance(reply, str)
    return reply


async def manage_with_mcp_tool(manager: MemoryManager, arguments: ManageArguments) -> str:
    server = MemoryMCPServer(manager, server_name="test-memory")
    result: object = await server.mcp.call_tool("memory_manage", dict(arguments))
    return "".join(str(getattr(block, "text", "")) for block in getattr(result, "content", []))


MANAGES = [pytest.param(manage_with_agent_tool, id="agent-tool"), pytest.param(manage_with_mcp_tool, id="mcp-tool")]
