"""The two surfaces an agent saves a memory through.

[INPUT]
- toolkits.memory.agent_surface.mcp_server::MemoryMCPServer (POS: MCP adapter exposing memory_store)
- toolkits.memory.agent_surface.memory_agent_tools::create_memory_tools (POS: in-process memory tools)
- toolkits.memory.manager::MemoryManager (POS: memory lifecycle manager)

[OUTPUT]
- Save / SaveArguments: one save call over a surface, and the arguments it takes
- save_with_agent_tool: save through the in-process ``memory_save_tool``
- save_with_mcp_tool: save through the MCP ``memory_store`` tool
- SAVES: both surfaces as pytest params

[POS]
Harness pytest-only driver shared by the save-tool tests, so a test states the arguments it saves with and runs
unchanged over both surfaces.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping

import pytest

from myrm_agent_harness.toolkits.memory.agent_surface.mcp_server import MemoryMCPServer
from myrm_agent_harness.toolkits.memory.agent_surface.memory_agent_tools import create_memory_tools
from myrm_agent_harness.toolkits.memory.manager import MemoryManager

type SaveArguments = Mapping[str, str | float]
type Save = Callable[[MemoryManager, SaveArguments], Awaitable[str]]


async def save_with_agent_tool(manager: MemoryManager, arguments: SaveArguments) -> str:
    tool = next(tool for tool in create_memory_tools(manager) if tool.name == "memory_save_tool")
    return await tool.ainvoke(dict(arguments))


async def save_with_mcp_tool(manager: MemoryManager, arguments: SaveArguments) -> str:
    result = await MemoryMCPServer(manager, server_name="test-memory").mcp.call_tool("memory_store", dict(arguments))
    return "".join(str(getattr(block, "text", "")) for block in result.content)


SAVES = [pytest.param(save_with_agent_tool, id="agent-tool"), pytest.param(save_with_mcp_tool, id="mcp-tool")]
