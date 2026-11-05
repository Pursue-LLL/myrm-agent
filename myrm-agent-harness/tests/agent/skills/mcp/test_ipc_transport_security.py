"""Security properties of the MCP IPC transport.

The socket sits in a shared temp directory on a multi-user host, and the script that writes to it is
model-generated code. These tests pin the properties that keep that from becoming a way out:

1. the socket is owner-only (0600) inside a 0700 directory;
2. a request must carry the server's bearer token;
3. a script execution cannot exceed its tool-call budget;
4. who the calls are made for (session, agent, workspace, read-only state, whether the code is a saved script)
   belongs to the server: a request that restates any of it is ignored, so a script cannot lift its own
   restrictions;
5. a saved script, whose code the host never reviewed, may call only tools declaring readOnlyHint.
"""

from __future__ import annotations

import asyncio
import json
import os
import stat
import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="Unix socket semantics")

from myrm_agent_harness.agent.skills.mcp.ipc_call_budget import CallBudget
from myrm_agent_harness.agent.skills.mcp.ipc_proxy import CallerScope, MCPIPCServer
from myrm_agent_harness.core.network.ipc_socket import execution_ipc_socket_path


def _server(scope: CallerScope | None = None, budget: CallBudget | None = None) -> MCPIPCServer:
    return MCPIPCServer(execution_ipc_socket_path(), scope or CallerScope(session_id="s1"), budget or CallBudget())


def _exchange(
    server: MCPIPCServer, bodies: list[dict[str, object]], *, authenticate: bool = True
) -> list[dict[str, object]]:
    """Start ``server``, send each body over one connection in order, stop the server."""

    async def _run() -> list[dict[str, object]]:
        await server.start()
        try:
            reader, writer = await asyncio.open_unix_connection(server.socket_path)
            responses: list[dict[str, object]] = []
            for body in bodies:
                token = {"auth_token": server.auth_token} if authenticate else {}
                payload = json.dumps({**token, **body}).encode()
                writer.write(len(payload).to_bytes(4, "big") + payload)
                await writer.drain()
                size = int.from_bytes(await reader.readexactly(4), "big")
                responses.append(json.loads(await reader.readexactly(size)))
            writer.close()
            await writer.wait_closed()
            return responses
        finally:
            await server.stop()

    return asyncio.run(_run())


def _notify(**extra: object) -> dict[str, object]:
    return {"skill_name": "__builtin__", "tool_name": "notify", "params": {"message": "m"}, **extra}


def test_socket_is_owner_only_inside_private_dir() -> None:
    server = _server()

    async def _run() -> tuple[int, int]:
        await server.start()
        try:
            return (
                stat.S_IMODE(os.stat(os.path.dirname(server.socket_path)).st_mode),
                stat.S_IMODE(os.stat(server.socket_path).st_mode),
            )
        finally:
            await server.stop()

    dir_mode, sock_mode = asyncio.run(_run())
    assert sock_mode == 0o600, f"socket mode {oct(sock_mode)} must be owner-only"
    assert dir_mode == 0o700, f"dir mode {oct(dir_mode)} must be owner-only"


def test_socket_paths_are_private_and_never_repeat() -> None:
    """A predictable shared path lets another local user pre-create the socket."""
    first, second = execution_ipc_socket_path(), execution_ipc_socket_path()

    assert first != second
    assert os.path.dirname(first) == os.path.dirname(second)
    assert str(os.getpid()) in first
    assert first != "/tmp/myrm-agent-mcp/mcp.sock"


def test_request_without_token_is_rejected() -> None:
    (body,) = _exchange(_server(), [_notify()], authenticate=False)

    assert body["success"] is False
    assert "unauthorized" in str(body["error"]).lower()


def test_request_with_wrong_token_is_rejected() -> None:
    (body,) = _exchange(_server(), [_notify(auth_token="not-the-token")])

    assert body["success"] is False
    assert "unauthorized" in str(body["error"]).lower()


def test_call_budget_is_enforced_per_execution_not_per_chat() -> None:
    """An execution that spends its budget must not lock the chat's later scripts out."""
    budget = CallBudget(max_calls_per_execution=2)
    scope = CallerScope(session_id="s1")

    first_script = _exchange(_server(scope, budget), [_notify() for i in range(3)])
    next_script = _exchange(_server(scope, budget), [_notify()])

    assert [r["success"] for r in first_script] == [True, True, False]
    assert "budget" in str(first_script[2]["error"]).lower()
    assert next_script[0]["success"] is True, "a new execution in the same chat gets a fresh budget"


def test_request_cannot_rekey_its_execution_budget() -> None:
    """The execution is the server's, so a script that rotates its trace id gains no calls."""
    server = _server(budget=CallBudget(max_calls_per_execution=2))

    responses = _exchange(server, [_notify(trace_id=f"fresh-{i}") for i in range(3)])

    assert [r["success"] for r in responses] == [True, True, False]
    assert "budget" in str(responses[2]["error"]).lower()


def test_request_cannot_rekey_its_session_ceiling() -> None:
    """The session is the server's: a script cannot spread its calls over invented sessions."""
    server = _server(CallerScope(session_id="real"), CallBudget(session_call_ceiling=2))

    responses = _exchange(server, [_notify(session_id=f"invented-{i}") for i in range(3)])

    assert [r["success"] for r in responses] == [True, True, False]
    assert "ceiling" in str(responses[2]["error"]).lower()


def _register_mcp_tool(*, read_only: bool) -> None:
    from myrm_agent_harness.core.security.tool_registry.registry import (
        register_ptc_safety_metadata,
    )
    from myrm_agent_harness.core.security.tool_registry.safety_table import SafetyMetadata

    register_ptc_safety_metadata(
        "mcp_demo_skill",
        "create-record",
        SafetyMetadata(is_read_only=read_only),
        {"readOnlyHint": read_only},
    )


def _create_record(**extra: object) -> dict[str, object]:
    return {"skill_name": "mcp_demo_skill", "tool_name": "create-record", "params": {}, **extra}


def test_read_only_scope_blocks_mutating_mcp_tool() -> None:
    """A read-only verifier must not mutate external state through a script."""
    _register_mcp_tool(read_only=False)
    server = _server(CallerScope(session_id="s1", readonly_workspace=True))

    (body,) = _exchange(server, [_create_record()])

    assert body["success"] is False
    assert "read-only" in str(body["error"]).lower()


def test_request_cannot_lift_the_read_only_scope() -> None:
    """The script writes the request itself, so it must not be able to say it is not read-only."""
    _register_mcp_tool(read_only=False)
    server = _server(CallerScope(session_id="s1", readonly_workspace=True))

    (body,) = _exchange(server, [_create_record(readonly_workspace=False)])

    assert body["success"] is False
    assert "read-only" in str(body["error"]).lower()


def test_read_only_scope_allows_read_only_mcp_tool() -> None:
    """readOnlyHint tools remain usable inside a read-only sandbox."""
    _register_mcp_tool(read_only=True)
    server = _server(CallerScope(session_id="s1", readonly_workspace=True))

    (body,) = _exchange(server, [_create_record()])

    # The tool has no real MCP config registered, so dispatch fails on lookup;
    # what matters is that the policy gate let the call through.
    assert "read-only" not in str(body.get("error") or "").lower()


def test_saved_script_scope_blocks_mutating_mcp_tool() -> None:
    """Only the command of a saved script was approved, so its code may not change external state."""
    _register_mcp_tool(read_only=False)
    server = _server(CallerScope(session_id="s1", script_file=True))

    (body,) = _exchange(server, [_create_record()])

    assert body["success"] is False
    error = str(body["error"]).lower()
    assert "saved script" in error
    assert "inline" in error, "the refusal must say where the call can be made"


def test_saved_script_scope_blocks_a_tool_without_safety_metadata() -> None:
    """A tool the host holds no readOnlyHint for is treated as mutating."""
    server = _server(CallerScope(session_id="s1", script_file=True))

    (body,) = _exchange(server, [{**_create_record(), "tool_name": "never-registered"}])

    assert body["success"] is False
    assert "saved script" in str(body["error"]).lower()


def test_request_cannot_lift_the_saved_script_scope() -> None:
    """The script writes the request itself, so it must not be able to say it is not a saved script."""
    _register_mcp_tool(read_only=False)
    server = _server(CallerScope(session_id="s1", script_file=True))

    (body,) = _exchange(server, [_create_record(script_file=False)])

    assert body["success"] is False
    assert "saved script" in str(body["error"]).lower()


def test_saved_script_scope_allows_read_only_mcp_tool() -> None:
    _register_mcp_tool(read_only=True)
    server = _server(CallerScope(session_id="s1", script_file=True))

    (body,) = _exchange(server, [_create_record()])

    # No real MCP config is registered, so dispatch fails on lookup; the policy gate let the call through.
    assert "saved script" not in str(body.get("error") or "").lower()


def test_saved_script_scope_allows_builtin_tools() -> None:
    server = _server(CallerScope(session_id="s1", script_file=True))

    (body,) = _exchange(server, [_notify()])

    assert body["success"] is True


def test_inline_scope_is_not_restricted_to_read_only_tools() -> None:
    """Inline Python is reviewed per call by the approval layer, so the IPC server does not second-guess it."""
    _register_mcp_tool(read_only=False)
    server = _server(CallerScope(session_id="s1"))

    (body,) = _exchange(server, [_create_record()])

    assert "saved script" not in str(body.get("error") or "").lower()


def test_call_budget_matches_track_two() -> None:
    """Both PTC tracks must expose one number with one meaning (calls per execution).

    A second, arbitrary ceiling makes the next reader ask why they differ and gives
    one track a looser bound than the other for no stated reason.
    """
    from myrm_agent_harness.agent.skills.mcp.ipc_call_budget import DEFAULT_MAX_CALLS_PER_EXECUTION
    from myrm_agent_harness.toolkits.code_execution.ptc.models import PtcConfig

    assert PtcConfig.model_fields["max_tool_calls"].default == DEFAULT_MAX_CALLS_PER_EXECUTION


def test_ipc_path_policy_blocks_path_outside_workspace() -> None:
    """Path policy must block path traversal outside the workspace in IPC calls."""
    server = _server(CallerScope(session_id="s1", workspace_root="/safe/workspace"))

    (body,) = _exchange(server, [_notify(params={"path": "/etc/passwd"})])

    assert body["success"] is False
    assert "path policy" in str(body["error"]).lower()


def test_request_cannot_widen_its_workspace() -> None:
    server = _server(CallerScope(session_id="s1", workspace_root="/safe/workspace"))

    (body,) = _exchange(server, [_notify(params={"path": "/etc/passwd"}, workspace_root="/")])

    assert body["success"] is False
    assert "path policy" in str(body["error"]).lower()


def test_generated_client_does_not_restate_the_callers_scope() -> None:
    """Session, agent, workspace and read-only state live on the server; the client never sends them."""
    from myrm_agent_harness.agent.skills.mcp.client_templates import generate_ipc_client_code

    code = generate_ipc_client_code("/tmp/agent.sock", auth_token="t", trace_nonce="n")

    for field in ("session_id", "agent_id", "workspace_root", "readonly_workspace"):
        assert field not in code, field


def _restrict_agent() -> None:
    from myrm_agent_harness.agent.sub_agents.mcp_scope_gate.scope_gate import (
        EmployeeScopedMcpDiscoveryGate,
    )
    from myrm_agent_harness.agent.sub_agents.mcp_scope_gate.types import (
        EmployeeToolScopePolicy,
    )

    EmployeeScopedMcpDiscoveryGate.get_instance().register_policy(
        EmployeeToolScopePolicy(agent_id="restricted_agent", allowed_mcp_servers=["12306"])
    )


def _github_read(**extra: object) -> dict[str, object]:
    return {"skill_name": "mcp_github_skill", "tool_name": "read_file", "params": {}, **extra}


def test_ipc_scope_gate_enforces_agent_allowlist() -> None:
    """Agent scope gate must block unapproved MCP tools for restricted agents."""
    _restrict_agent()
    server = _server(CallerScope(session_id="user-1_chat-1", agent_id="restricted_agent"))

    (body,) = _exchange(server, [_github_read()])

    assert body["success"] is False
    assert "agent scope" in str(body["error"]).lower()


def test_request_cannot_borrow_another_agents_scope() -> None:
    _restrict_agent()
    server = _server(CallerScope(session_id="user-1_chat-1", agent_id="restricted_agent"))

    (body,) = _exchange(server, [_github_read(agent_id="some-unrestricted-agent")])

    assert body["success"] is False
    assert "agent scope" in str(body["error"]).lower()
