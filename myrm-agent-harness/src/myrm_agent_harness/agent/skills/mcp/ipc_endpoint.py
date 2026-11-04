"""Lifetime of the MCP IPC server: one per script execution

[INPUT]
- ipc_proxy::CallerScope, IPCEndpoint, MCPIPCServer (POS: the server and what the client needs to reach it)
- ipc_call_budget::CallBudget (POS: admission control)
- core.network.ipc_socket::execution_ipc_socket_path (POS: private per-execution socket path)

[OUTPUT]
- mcp_ipc_endpoint: Async context manager that serves one script execution.

[POS]
A server that lives exactly as long as the execution it serves runs on the loop of that execution, so it can
neither outlive its loop nor be shared between two executions.
"""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from myrm_agent_harness.agent.skills.mcp.ipc_call_budget import (
    DEFAULT_MAX_CALLS_PER_EXECUTION,
    DEFAULT_SESSION_CALL_CEILING,
    CallBudget,
)
from myrm_agent_harness.agent.skills.mcp.ipc_proxy import CallerScope, IPCEndpoint, MCPIPCServer
from myrm_agent_harness.core.network.ipc_socket import execution_ipc_socket_path

_SESSION_BUDGET = CallBudget(DEFAULT_MAX_CALLS_PER_EXECUTION, DEFAULT_SESSION_CALL_CEILING)
"""Shared by every server: the per-session ceiling has to add up across the scripts of one chat."""


async def _stop_once_started(server: MCPIPCServer, start: asyncio.Future[None]) -> None:
    """Let a start that was cancelled midway finish, then stop what it opened.

    ``start()`` has a cancellation point after the listener is already bound; cancelling there would
    leave a socket and its file nobody owns.
    """
    await asyncio.gather(start, return_exceptions=True)
    await server.stop()


@asynccontextmanager
async def mcp_ipc_endpoint(scope: CallerScope) -> AsyncIterator[IPCEndpoint]:
    """Serve one script execution: start a server on the running loop and stop it when the execution ends."""
    server = MCPIPCServer(execution_ipc_socket_path(), scope, _SESSION_BUDGET)
    start = asyncio.ensure_future(server.start())
    try:
        try:
            await asyncio.shield(start)
        except OSError as e:
            raise RuntimeError(f"Failed to start MCP IPC server at {server.socket_path}: {e}") from e
        yield server.endpoint
    finally:
        await asyncio.shield(_stop_once_started(server, start))
