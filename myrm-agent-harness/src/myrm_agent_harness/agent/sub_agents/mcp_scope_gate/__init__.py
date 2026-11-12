"""Employee/Agent-Scoped MCP Tool Discovery Gate package.

[INPUT]
- agent.sub_agents.mcp_scope_gate.scope_gate::EmployeeScopedMcpDiscoveryGate (POS: Fail-closed enforcement point of the MCP scope gate: a thread-safe in-memory registry of per-agent scope policies that filters dynamically discovered MCP tools and verifies each invocation against the agent's allowed servers and tool allowlists.)
- agent.sub_agents.mcp_scope_gate.types::EmployeeToolScopePolicy, EmployeeToolScopeViolationError, McpDiscoveryCheckResult, ScopedMcpFilterVerdict (POS: Contract layer of the MCP scope gate: the per-agent scope policy, the per-tool and batch check results, and the violation error raised on an out-of-scope call.)

[OUTPUT]
- EmployeeScopedMcpDiscoveryGate
- EmployeeToolScopePolicy, McpDiscoveryCheckResult, ScopedMcpFilterVerdict
- EmployeeToolScopeViolationError

[POS]
Package facade of the MCP scope gate: the single import point for the gate, the scope policy, the check and verdict results and
the violation error.
"""

from myrm_agent_harness.agent.sub_agents.mcp_scope_gate.scope_gate import (
    EmployeeScopedMcpDiscoveryGate,
)
from myrm_agent_harness.agent.sub_agents.mcp_scope_gate.types import (
    EmployeeToolScopePolicy,
    EmployeeToolScopeViolationError,
    McpDiscoveryCheckResult,
    ScopedMcpFilterVerdict,
)

__all__ = [
    "EmployeeScopedMcpDiscoveryGate",
    "EmployeeToolScopePolicy",
    "EmployeeToolScopeViolationError",
    "McpDiscoveryCheckResult",
    "ScopedMcpFilterVerdict",
]
