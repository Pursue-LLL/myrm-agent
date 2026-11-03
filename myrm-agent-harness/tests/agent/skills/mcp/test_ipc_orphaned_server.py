"""A global IPC server whose event loop closed must be replaced, not reused.

Its listening socket stays open after the loop closes, so a client connects without
error and then waits forever for a reply nobody sends. The fixture builds the orphan two
ways: ``asyncio.run`` returning, and a loop closed while a client is still connected and
its handler task is still pending (stopping that one must not await the dead loop).
"""

from __future__ import annotations

import asyncio
import gc
import json
import os
import socket
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


def _tokenless_frame() -> bytes:
    payload = MCPIPCRequest(skill_name="s", tool_name="t", params={}).model_dump_json().encode()
    return len(payload).to_bytes(4, "big") + payload


def _orphan_by_asyncio_run() -> MCPIPCServer:
    return asyncio.run(start_mcp_ipc_server(default_ipc_socket_path()))


async def _hold_a_connection_after_one_reply(client: socket.socket, socket_path: str) -> None:
    """A raw socket, not a stream, so the connection outlives the loop that served it."""
    loop = asyncio.get_running_loop()
    await loop.sock_connect(client, socket_path)
    await loop.sock_sendall(client, _tokenless_frame())
    async with asyncio.timeout(_REPLY_DEADLINE_SECONDS):
        await loop.sock_recv(client, 1)


def _orphan_with_a_client_attached(client: socket.socket) -> MCPIPCServer:
    loop = asyncio.new_event_loop()
    try:
        server = loop.run_until_complete(start_mcp_ipc_server(default_ipc_socket_path()))
        loop.run_until_complete(_hold_a_connection_after_one_reply(client, server.socket_path))
    finally:
        loop.close()
    return server


@pytest.fixture(params=["after_asyncio_run", "with_a_client_attached"])
def orphaned_server(request: pytest.FixtureRequest) -> Iterator[MCPIPCServer]:
    """The global server, left running on a loop that is already closed."""
    asyncio.run(stop_mcp_ipc_server())
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.setblocking(False)
    try:
        if request.param == "after_asyncio_run":
            yield _orphan_by_asyncio_run()
        else:
            yield _orphan_with_a_client_attached(client)
    finally:
        client.close()
        asyncio.run(stop_mcp_ipc_server())
        # asyncio reports the dead loop's pending handler when it is collected: collect it here so the
        # report lands in this test's captured log instead of on the session's stderr.
        gc.collect()


async def _reply_to_a_tokenless_request(socket_path: str) -> dict[str, object]:
    """Any server that is served refuses a request without a token; an orphan never replies."""
    reader, writer = await asyncio.open_unix_connection(socket_path)
    try:
        writer.write(_tokenless_frame())
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


def test_stopping_an_orphan_frees_its_socket_path(orphaned_server: MCPIPCServer) -> None:
    asyncio.run(stop_mcp_ipc_server())

    assert get_mcp_ipc_server() is None
    assert not os.path.exists(orphaned_server.socket_path)
