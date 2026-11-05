"""Per-request policy gates of the MCP IPC server

Each gate inspects one script-originated request against the scope the host gave the server and returns an error
message when the request must be refused, else ``None``. The scope, never the request, says whose run this is. They
hold no server state, so they live apart from the connection handling in ``ipc_proxy``.

[INPUT]
- ipc_proxy.MCPIPCRequest, CallerScope (type only): The request under inspection and the run it belongs to.

[OUTPUT]
- read_only_policy_error: Read-only sandbox scope for MCP calls made from scripts.
- script_file_policy_error: Read-only limit for scripts started from a saved file, whose code the host never reviewed.
- path_policy_error: Workspace path policy for tool parameters naming a path.
- scope_gate_error: Employee/agent-scoped MCP discovery gate.
- REQUEST_GATES: The gates in the order the server applies them, each with the name its refusal is logged under.

[POS]
Authorization policy of the PTC IPC backbone; ``MCPIPCServer._process_request`` applies ``REQUEST_GATES`` in order.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from myrm_agent_harness.agent.skills.mcp.ipc_proxy import CallerScope, MCPIPCRequest


def _declares_read_only(request: MCPIPCRequest) -> bool:
    """True for builtins (they do not touch external state) and for MCP tools declaring readOnlyHint.

    A tool the host holds no safety metadata for counts as mutating (fail-closed).
    """
    from myrm_agent_harness.agent.skills.mcp.builtin_registry import BUILTIN_SKILL_NAME
    from myrm_agent_harness.core.security.tool_registry.registry import (
        get_ptc_safety_metadata,
    )

    if request.skill_name == BUILTIN_SKILL_NAME:
        return True
    entry = get_ptc_safety_metadata(request.skill_name, request.tool_name)
    return entry is not None and entry[0].is_read_only


def read_only_policy_error(request: MCPIPCRequest, scope: CallerScope) -> str | None:
    """Enforce the caller's read-only scope on MCP calls made from scripts.

    The direct Function-Calling path drops or blocks non-read-only MCP tools
    inside a read-only sandbox. Scripts bypassed that filtering entirely, so a
    read-only verifier could still mutate external state through PTC. This is
    the enforcement point for that path.

    Returns an error message when blocked, else ``None``.
    """
    if not scope.readonly_workspace or _declares_read_only(request):
        return None
    return (
        f"MCP tool '{request.skill_name}.{request.tool_name}' is blocked: the calling run "
        "is in a read-only sandbox. Only tools declaring readOnlyHint may run here."
    )


def script_file_policy_error(request: MCPIPCRequest, scope: CallerScope) -> str | None:
    """Limit a saved script to read-only MCP tools.

    Inline Python is approved call by call from its own code, so a mutating MCP tool is reviewed before it runs. A
    saved script reaches the server as a plain ``python file.py`` command: the approval covers the command, not the
    file's code, so letting it mutate would hand the model a way around that review.

    Returns an error message when blocked, else ``None``.
    """
    if not scope.script_file or _declares_read_only(request):
        return None
    return (
        f"MCP tool '{request.skill_name}.{request.tool_name}' is blocked: this code runs from a saved script, "
        "and a saved script may only call tools declaring readOnlyHint. "
        "Call it from inline Python in bash_code_execute_tool instead."
    )


def path_policy_error(request: MCPIPCRequest, scope: CallerScope) -> str | None:
    """Enforce workspace path policy on tool calls made from scripts."""
    if not scope.workspace_root or not isinstance(request.params, dict):
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

    action, reason = check_path_policy(target_path, PathPolicy(), scope.workspace_root)
    if action == PermissionAction.DENY:
        return f"Path policy violation: {reason}"
    return None


def scope_gate_error(request: MCPIPCRequest, scope: CallerScope) -> str | None:
    """Enforce employee/agent-scoped MCP discovery gate policies."""
    from myrm_agent_harness.agent.sub_agents.mcp_scope_gate.scope_gate import (
        EmployeeScopedMcpDiscoveryGate,
    )
    from myrm_agent_harness.agent.sub_agents.mcp_scope_gate.types import (
        EmployeeToolScopeViolationError,
    )

    agent_id = scope.agent_id
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


REQUEST_GATES: tuple[tuple[str, Callable[[MCPIPCRequest, CallerScope], str | None]], ...] = (
    ("read-only policy", read_only_policy_error),
    ("saved-script policy", script_file_policy_error),
    ("path policy", path_policy_error),
    ("agent scope gate", scope_gate_error),
)
