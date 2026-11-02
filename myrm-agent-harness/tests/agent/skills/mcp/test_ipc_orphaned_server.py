"""A global IPC server whose event loop closed must be replaced, not reused.

Its listening socket stays open after the loop closes, so a client connects without
error and then waits forever for a reply nobody sends. The fixture builds the orphan
with ``asyncio.run``: the loop it runs on is closed once the call returns.
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import Iterator

import pytest

from myrm_agent_harness.agent.skills.mcp.ipc_proxy import (
    MCPIPCRequest,
    MCPIPCServer,
    get_mcp_ipc_server,
    get_mcp_trace_nonce,
    start_mcp_ipc_server,
    stop_mcp_ipc_server,
)
from myrm_agent_harness.core.network.ipc_socket import default_ipc_socket_path

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="Unix socket semantics")

_REPLY_DEADLINE_SECONDS = 5


@pytest.fixture
def orphaned_server() -> Iterator[MCPIPCServer]:
    """The global server, left running on a loop that is already closed."""
    asyncio.run(stop_mcp_ipc_server())
    yield asyncio.run(start_mcp_ipc_server(default_ipc_socket_path()))
    asyncio.run(stop_mcp_ipc_server())


async def _reply_to_a_tokenless_request(socket_path: str) -> dict[str, object]:
    """Any server that is served refuses a request without a token; an orphan never replies."""
    reader, writer = await asyncio.open_unix_connection(socket_path)
    try:
        payload = MCPIPCRequest(skill_name="s", tool_name="t", params={}).model_dump_json().encode()
        writer.write(len(payload).to_bytes(4, "big") + payload)
        await writer.drain()
        async with asyncio.timeout(_REPLY_DEADLINE_SECONDS):
            length = int.from_bytes(await reader.readexactly(4), "big")
            reply: dict[str, object] = json.loads(await reader.readexactly(length))
            return reply
    finally:
        writer.close()


def test_an_orphaned_server_is_neither_offered_nor_trusted(orphaned_server: MCPIPCServer) -> None:
    assert orphaned_server.is_orphaned
    assert get_mcp_ipc_server() is None
    assert get_mcp_trace_nonce() is None


def test_a_server_started_after_an_orphan_answers_requests(orphaned_server: MCPIPCServer) -> None:
    async def scenario() -> tuple[MCPIPCServer, dict[str, object]]:
        try:
            server = await start_mcp_ipc_server(default_ipc_socket_path())
            return server, await _reply_to_a_tokenless_request(server.socket_path)
        finally:
            await stop_mcp_ipc_server()

    replacement, reply = asyncio.run(scenario())

    assert replacement is not orphaned_server
    assert reply["success"] is False
    assert "Unauthorized" in str(reply["error"])
