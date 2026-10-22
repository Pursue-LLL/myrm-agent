"""
[INPUT]
- myrm_agent_harness.agent.sub_agents.mcp_scope_gate.*
- app.schemas.mcp_scope_gate.*

[OUTPUT]
- McpScopeGateService

[POS]
Server 业务层 MCP 发现工具按数字员工/Agent 作用域严格隔离门禁服务（Topic 12 · 第 20 项）。
聚合 Harness 层的 EmployeeScopedMcpDiscoveryGate，提供策略维护、动态工具候选集裁剪与调用鉴权门禁。
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from myrm_agent_harness.agent.sub_agents.mcp_scope_gate import (
    EmployeeScopedMcpDiscoveryGate,
    EmployeeToolScopePolicy,
    EmployeeToolScopeViolationError,
)

from app.schemas.mcp_scope_gate import (
    EmployeeToolScopePolicyDTO,
    McpDiscoveryCheckResultDTO,
    McpToolCandidateDTO,
    ScopedMcpFilterVerdictDTO,
    VerifyToolCallResponseDTO,
)

logger = logging.getLogger(__name__)


class McpScopeGateService:
    """Service governing employee-scoped MCP tool discovery filtering and invocation authorization."""

    def __init__(self, gate: EmployeeScopedMcpDiscoveryGate | None = None) -> None:
        self._gate = gate or EmployeeScopedMcpDiscoveryGate.get_instance()

    def register_or_update_policy(self, policy_dto: EmployeeToolScopePolicyDTO) -> EmployeeToolScopePolicyDTO:
        """Register or update a tool scope policy for an agent."""
        updated_time = policy_dto.updated_at or datetime.now(UTC).isoformat()
        domain_policy = EmployeeToolScopePolicy(
            agent_id=policy_dto.agent_id,
            allowed_mcp_servers=list(policy_dto.allowed_mcp_servers),
            tool_allowlist_map=dict(policy_dto.tool_allowlist_map),
            strict_mode=policy_dto.strict_mode,
            updated_at=updated_time,
        )
        self._gate.register_policy(domain_policy)

        return EmployeeToolScopePolicyDTO(
            agent_id=domain_policy.agent_id,
            allowed_mcp_servers=domain_policy.allowed_mcp_servers,
            tool_allowlist_map=domain_policy.tool_allowlist_map,
            strict_mode=domain_policy.strict_mode,
            updated_at=domain_policy.updated_at,
        )

    def get_policy(self, agent_id: str) -> EmployeeToolScopePolicyDTO | None:
        """Retrieve the registered scope policy for an agent."""
        policy = self._gate.get_policy(agent_id)
        if not policy:
            return None

        return EmployeeToolScopePolicyDTO(
            agent_id=policy.agent_id,
            allowed_mcp_servers=policy.allowed_mcp_servers,
            tool_allowlist_map=policy.tool_allowlist_map,
            strict_mode=policy.strict_mode,
            updated_at=policy.updated_at,
        )

    def filter_discovered_tools(self, agent_id: str, candidates: list[McpToolCandidateDTO]) -> ScopedMcpFilterVerdictDTO:
        """Filter dynamically discovered MCP candidate tools against the agent's scope policy."""
        tuples_list = [(c.server_name, c.tool_name, c.description) for c in candidates]
        verdict = self._gate.filter_discovered_tools(agent_id, tuples_list)

        allowed_dtos = [
            McpDiscoveryCheckResultDTO(
                server_name=t.server_name,
                tool_name=t.tool_name,
                is_allowed=t.is_allowed,
                reason=t.reason,
                description=t.description,
            )
            for t in verdict.allowed_tools
        ]
        blocked_dtos = [
            McpDiscoveryCheckResultDTO(
                server_name=t.server_name,
                tool_name=t.tool_name,
                is_allowed=t.is_allowed,
                reason=t.reason,
                description=t.description,
            )
            for t in verdict.blocked_tools
        ]

        return ScopedMcpFilterVerdictDTO(
            agent_id=agent_id,
            total_discovered=verdict.total_discovered,
            allowed_count=verdict.allowed_count,
            blocked_count=verdict.blocked_count,
            allowed_tools=allowed_dtos,
            blocked_tools=blocked_dtos,
        )

    def verify_tool_call(self, agent_id: str, server_name: str, tool_name: str) -> VerifyToolCallResponseDTO:
        """Verify whether an agent is permitted to invoke a target MCP tool."""
        try:
            check_res = self._gate.verify_tool_invocation(agent_id, server_name, tool_name)
            return VerifyToolCallResponseDTO(
                agent_id=agent_id,
                server_name=server_name,
                tool_name=tool_name,
                is_allowed=True,
                reason=check_res.reason,
            )
        except EmployeeToolScopeViolationError as exc:
            return VerifyToolCallResponseDTO(
                agent_id=agent_id,
                server_name=server_name,
                tool_name=tool_name,
                is_allowed=False,
                reason=exc.reason,
            )
