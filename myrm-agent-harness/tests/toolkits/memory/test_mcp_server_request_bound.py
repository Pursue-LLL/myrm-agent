"""Request-bound mode of MemoryMCPServer: no default MemoryManager at construction.

The HTTP layer of a multi-agent deployment binds a manager per request, so the server
must build without opening any storage or embedding backend, and an unbound request
must fail loudly instead of reaching a stand-in manager.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from myrm_agent_harness.toolkits.memory.agent_surface._memory_agent_tool_descriptions import (
    build_mcp_memory_store_tool_description,
)
from myrm_agent_harness.toolkits.memory.agent_surface.mcp_server import (
    MemoryMCPServer,
    reset_request_memory_manager,
    set_request_memory_manager,
)
from myrm_agent_harness.toolkits.memory.types import MemorySearchResult, MemoryType, SemanticMemory


def _manager(*, approval_required: bool = False) -> AsyncMock:
    manager = AsyncMock()
    manager.search = AsyncMock(
        return_value=[
            MemorySearchResult(memory=SemanticMemory(content="bound fact"), score=0.9, memory_type=MemoryType.SEMANTIC)
        ]
    )
    manager.has_relational = True
    manager.has_vector = True
    manager.approval_required = approval_required
    manager.get_enabled_types = MagicMock(return_value=[MemoryType.SEMANTIC])
    return manager


def _text(result: object) -> str:
    return "".join(str(getattr(block, "text", "")) for block in getattr(result, "content", []))


async def _store_description(server: MemoryMCPServer) -> str:
    tools = {tool.name: tool for tool in await server.mcp.list_tools()}
    return tools["memory_store"].description or ""


@pytest.mark.asyncio
async def test_server_builds_without_default_manager() -> None:
    server = MemoryMCPServer(approval_required=False, stateless_http=True)

    names = sorted(tool.name for tool in await server.mcp.list_tools())

    assert names == ["memory_list", "memory_manage", "memory_recall", "memory_store"]


@pytest.mark.asyncio
async def test_store_description_follows_the_explicit_approval_flag() -> None:
    server = MemoryMCPServer(approval_required=True)

    description = await _store_description(server)

    assert description == build_mcp_memory_store_tool_description(approval_required=True)
    assert description != build_mcp_memory_store_tool_description(approval_required=False)


@pytest.mark.asyncio
async def test_explicit_flag_wins_over_the_default_manager_flag() -> None:
    server = MemoryMCPServer(_manager(approval_required=False), approval_required=True)

    assert await _store_description(server) == build_mcp_memory_store_tool_description(approval_required=True)


@pytest.mark.asyncio
async def test_default_manager_flag_is_used_when_none_is_given() -> None:
    server = MemoryMCPServer(_manager(approval_required=True))

    assert await _store_description(server) == build_mcp_memory_store_tool_description(approval_required=True)


def test_approval_flag_is_required_without_a_default_manager() -> None:
    with pytest.raises(ValueError, match="approval_required"):
        MemoryMCPServer()


@pytest.mark.asyncio
async def test_request_bound_manager_serves_calls_without_default() -> None:
    server = MemoryMCPServer(approval_required=False)
    bound = _manager()

    token = set_request_memory_manager(bound)
    try:
        result = _text(await server.mcp.call_tool("memory_recall", {"query": "anything"}))
    finally:
        reset_request_memory_manager(token)

    assert "bound fact" in result
    bound.search.assert_called_once()


@pytest.mark.asyncio
async def test_unbound_request_fails_instead_of_reaching_a_stand_in_manager() -> None:
    server = MemoryMCPServer(approval_required=False)

    with pytest.raises(ToolError) as raised:
        await server.mcp.call_tool("memory_recall", {"query": "anything"})

    # The MCP runtime wraps the failure; whether the wrapper's own message repeats the original
    # text depends on the runtime version, so the original error is read from its cause.
    assert "No MemoryManager is bound" in str(raised.value.__cause__)
