"""Per-request policy gates of the MCP IPC server

Each gate inspects one script-originated request and returns an error message when the request must be refused, else
``None``. They hold no server state, so they live apart from the connection handling in ``ipc_proxy``.

[INPUT]
- ipc_proxy.MCPIPCRequest (type only): The request under inspection.

[OUTPUT]
- read_only_policy_error: Read-only sandbox scope for MCP calls made from scripts.
- path_policy_error: Workspace path policy for tool parameters naming a path.
- scope_gate_error: Employee/agent-scoped MCP discovery gate.

[POS]
Authorization policy of the PTC IPC backbone; ``MCPIPCServer._process_request`` applies the gates in this order.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from myrm_agent_harness.agent.skills.mcp.ipc_proxy import MCPIPCRequest


def read_only_policy_error(request: MCPIPCRequest) -> str | None:
    """Enforce the caller's read-only scope on MCP calls made from scripts.

    The direct Function-Calling path drops or blocks non-read-only MCP tools
    inside a read-only sandbox. Scripts bypassed that filtering entirely, so a
    read-only verifier could still mutate external state through PTC. This is
    the enforcement point for that path.

    Returns an error message when blocked, else ``None``.
    """
    from myrm_agent_harness.agent.skills.mcp.builtin_registry import BUILTIN_SKILL_NAME

    # Builtins (notify) do not touch external state.
    if not request.readonly_workspace or request.skill_name == BUILTIN_SKILL_NAME:
        return None

    from myrm_agent_harness.core.security.tool_registry.registry import (
        get_ptc_safety_metadata,
    )

    entry = get_ptc_safety_metadata(request.skill_name, request.tool_name)
    if entry is not None and entry[0].is_read_only:
        return None
    return (
        f"MCP tool '{request.skill_name}.{request.tool_name}' is blocked: the calling run "
        "is in a read-only sandbox. Only tools declaring readOnlyHint may run here."
    )


def path_policy_error(request: MCPIPCRequest) -> str | None:
    """Enforce workspace path policy on tool calls made from scripts."""
    if not request.workspace_root or not isinstance(request.params, dict):
        return None

    path_keys = ("path", "file_path", "target", "destination", "filepath")
    target_path = None
    for k in path_keys:
        val = request.params.get(k)
        if isinstance(val, str) and val.strip():
            target_path = val.strip()
            break
    if not target_path:
        return None

    from myrm_agent_harness.agent.security.checks import check_path_policy
    from myrm_agent_harness.agent.security.types import PathPolicy, PermissionAction

    action, reason = check_path_policy(target_path, PathPolicy(), request.workspace_root)
    if action == PermissionAction.DENY:
        return f"Path policy violation: {reason}"
    return None


def scope_gate_error(request: MCPIPCRequest) -> str | None:
    """Enforce employee/agent-scoped MCP discovery gate policies."""
    from myrm_agent_harness.agent.sub_agents.mcp_scope_gate.scope_gate import (
        EmployeeScopedMcpDiscoveryGate,
    )
    from myrm_agent_harness.agent.sub_agents.mcp_scope_gate.types import (
        EmployeeToolScopeViolationError,
    )

    agent_id = request.agent_id
    if not agent_id:
        return None

    gate = EmployeeScopedMcpDiscoveryGate.get_instance()
    if not gate.get_policy(agent_id):
        return None

    server_name = request.skill_name
    if server_name.startswith("mcp_") and server_name.endswith("_skill"):
        server_name = server_name[4:-6]

    try:
        gate.verify_tool_invocation(agent_id, server_name, request.tool_name)
    except EmployeeToolScopeViolationError as e:
        return f"Agent scope violation: {e.reason}"
    return None
