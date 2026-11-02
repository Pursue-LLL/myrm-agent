"""Unit tests for MCP IPC server lifecycle and guard edge cases.

[INPUT]
- myrm_agent_harness.agent.skills.mcp.ipc_proxy (POS: IPC server, guards, globals)

[OUTPUT]
- Coverage for already-running/stopped lifecycle, path/scope gate early returns,
  and global server start/stop accessors.

[POS]
IPC proxy edge-case tests. No sandbox or real MCP server is spawned.
"""

from __future__ import annotations

import asyncio
import shutil
import tempfile
from pathlib import Path

from myrm_agent_harness.agent.skills.mcp.ipc_proxy import (
    MCPIPCRequest,
    MCPIPCServer,
    get_mcp_ipc_server,
    get_mcp_trace_nonce,
    start_mcp_ipc_server,
    stop_mcp_ipc_server,
)
from myrm_agent_harness.agent.skills.mcp.ipc_request_policy import path_policy_error, scope_gate_error


def test_start_is_idempotent_when_already_running(tmp_path: Path) -> None:
    server = MCPIPCServer(str(tmp_path / "already.sock"))
    server._running = True

    asyncio.run(server.start())

    assert server._running is True
    assert server._server is None


def test_stop_is_noop_when_not_running(tmp_path: Path) -> None:
    server = MCPIPCServer(str(tmp_path / "stopped.sock"))

    asyncio.run(server.stop())

    assert server._running is False


def test_path_policy_skips_request_without_path(tmp_path: Path) -> None:
    request = MCPIPCRequest(skill_name="mcp_demo_skill", tool_name="read", params={}, workspace_root=str(tmp_path))

    assert path_policy_error(request) is None


def test_path_policy_allows_path_inside_workspace(tmp_path: Path) -> None:
    allowed = tmp_path / "inside.txt"
    allowed.write_text("ok", encoding="utf-8")
    request = MCPIPCRequest(
        skill_name="mcp_demo_skill",
        tool_name="read",
        params={"path": str(allowed)},
        workspace_root=str(tmp_path),
    )

    assert path_policy_error(request) is None


def test_scope_gate_skips_without_agent_or_policy() -> None:
    no_agent = MCPIPCRequest(skill_name="mcp_demo_skill", tool_name="read", params={}, agent_id=None)
    unknown_agent = MCPIPCRequest(
        skill_name="mcp_demo_skill",
        tool_name="read",
        params={},
        agent_id="agent-without-policy",
    )

    assert scope_gate_error(no_agent) is None
    assert scope_gate_error(unknown_agent) is None


def test_global_server_lifecycle_and_trace_nonce() -> None:
    socket_dir = tempfile.mkdtemp(prefix="ipc-", dir="/tmp")
    socket_path = f"{socket_dir}/s.sock"
    asyncio.run(stop_mcp_ipc_server())

    async def run() -> None:
        try:
            server = await start_mcp_ipc_server(socket_path)
            assert get_mcp_ipc_server() is server
            assert get_mcp_trace_nonce() == server.trace_nonce
            assert await start_mcp_ipc_server(socket_path) is server
        finally:
            await stop_mcp_ipc_server()

    asyncio.run(run())
    shutil.rmtree(socket_dir, ignore_errors=True)

    assert get_mcp_ipc_server() is None
    assert get_mcp_trace_nonce() is None
