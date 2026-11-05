"""Unit tests for MCP IPC server lifecycle and guard edge cases.

[INPUT]
- myrm_agent_harness.agent.skills.mcp.ipc_proxy (POS: IPC server, caller scope)
- myrm_agent_harness.agent.skills.mcp.ipc_request_policy (POS: authorization gates)

[OUTPUT]
- Coverage for already-running/stopped lifecycle, path/scope gate early returns and the gate order.

[POS]
IPC proxy edge-case tests. No sandbox or real MCP server is spawned.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from myrm_agent_harness.agent.skills.mcp.ipc_call_budget import CallBudget
from myrm_agent_harness.agent.skills.mcp.ipc_proxy import CallerScope, MCPIPCRequest, MCPIPCServer
from myrm_agent_harness.agent.skills.mcp.ipc_request_policy import (
    REQUEST_GATES,
    path_policy_error,
    scope_gate_error,
    script_file_policy_error,
)


def _server(tmp_path: Path, name: str) -> MCPIPCServer:
    return MCPIPCServer(str(tmp_path / name), CallerScope(), CallBudget())


def _request(**params: object) -> MCPIPCRequest:
    return MCPIPCRequest(skill_name="mcp_demo_skill", tool_name="read", params=params)


def test_start_is_idempotent_when_already_running(tmp_path: Path) -> None:
    server = _server(tmp_path, "already.sock")
    server._running = True

    asyncio.run(server.start())

    assert server._running is True
    assert server._server is None


def test_stop_is_noop_when_never_started(tmp_path: Path) -> None:
    server = _server(tmp_path, "stopped.sock")

    asyncio.run(server.stop())
    asyncio.run(server.stop())

    assert server._running is False


def test_path_policy_skips_request_without_path(tmp_path: Path) -> None:
    assert path_policy_error(_request(), CallerScope(workspace_root=str(tmp_path))) is None


def test_path_policy_allows_path_inside_workspace(tmp_path: Path) -> None:
    allowed = tmp_path / "inside.txt"
    allowed.write_text("ok", encoding="utf-8")

    assert path_policy_error(_request(path=str(allowed)), CallerScope(workspace_root=str(tmp_path))) is None


def test_path_policy_skips_a_scope_without_workspace(tmp_path: Path) -> None:
    assert path_policy_error(_request(path=str(tmp_path / "any.txt")), CallerScope()) is None


def test_scope_gate_skips_without_agent_or_policy() -> None:
    assert scope_gate_error(_request(), CallerScope(agent_id=None)) is None
    assert scope_gate_error(_request(), CallerScope(agent_id="agent-without-policy")) is None


def test_script_file_policy_skips_a_scope_that_is_not_a_saved_script() -> None:
    assert script_file_policy_error(_request(), CallerScope()) is None


def test_request_gates_keep_their_documented_order() -> None:
    assert [name for name, _ in REQUEST_GATES] == [
        "read-only policy",
        "saved-script policy",
        "path policy",
        "agent scope gate",
    ]
