"""
[INPUT]
- app.schemas.mcp_scope_gate.*
- app.services.agent.mcp_scope_gate_service.McpScopeGateService
- fastapi (APIRouter, Depends, Path)

[OUTPUT]
- router (MCP Scope Gate API Router)
- POST /agents/{agent_id}/mcp-scope/policy
- GET /agents/{agent_id}/mcp-scope/policy
- POST /agents/{agent_id}/mcp-scope/filter-discovered
- POST /agents/{agent_id}/mcp-scope/verify-call

[POS]
Server 业务层数字员工 MCP 工具作用域隔离门禁 REST 路由（Topic 12 · 第 20 项）。
提供作用域策略 CRUD、动态发现工具裁剪过滤与单次工具调用鉴权 API 端点。
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Path
from fastapi.responses import JSONResponse

from app.core.utils.response_utils import error_response, success_response
from app.schemas.mcp_scope_gate import (
    EmployeeToolScopePolicyDTO,
    ScopedMcpFilterRequestDTO,
    ScopedMcpFilterVerdictDTO,
    VerifyToolCallRequestDTO,
    VerifyToolCallResponseDTO,
)
from app.services.agent.mcp_scope_gate_service import McpScopeGateService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agents/{agent_id}/mcp-scope", tags=["Employee Scoped MCP Gate"])

_mcp_scope_gate_service_instance: McpScopeGateService | None = None


def get_mcp_scope_gate_service() -> McpScopeGateService:
    """Dependency injector for McpScopeGateService."""
    global _mcp_scope_gate_service_instance
    if _mcp_scope_gate_service_instance is None:
        _mcp_scope_gate_service_instance = McpScopeGateService()
    return _mcp_scope_gate_service_instance


@router.post("/policy", response_model=EmployeeToolScopePolicyDTO)
async def register_or_update_scope_policy(
    agent_id: Annotated[str, Path(..., description="Target agent profile ID")],
    policy: EmployeeToolScopePolicyDTO,
    service: Annotated[McpScopeGateService, Depends(get_mcp_scope_gate_service)],
) -> JSONResponse:
    """Register or update an agent profile's MCP tool access scope policy."""
    try:
        if policy.agent_id != agent_id:
            policy.agent_id = agent_id
        saved_policy = service.register_or_update_policy(policy)
        return success_response(data=saved_policy.model_dump())
    except Exception as exc:
        logger.exception("Failed to register MCP scope policy for agent %s", agent_id)
        return error_response(
            message=f"Failed to register MCP scope policy: {exc}",
            status_code=500,
        )


@router.get("/policy", response_model=EmployeeToolScopePolicyDTO)
async def get_agent_scope_policy(
    agent_id: Annotated[str, Path(..., description="Target agent profile ID")],
    service: Annotated[McpScopeGateService, Depends(get_mcp_scope_gate_service)],
) -> JSONResponse:
    """Fetch the active MCP tool scope policy for an agent."""
    try:
        policy = service.get_policy(agent_id)
        if not policy:
            return error_response(
                message=f"No MCP scope policy found for agent {agent_id}",
                status_code=404,
            )
        return success_response(data=policy.model_dump())
    except Exception as exc:
        logger.exception("Failed to get MCP scope policy for agent %s", agent_id)
        return error_response(
            message=f"Failed to get MCP scope policy: {exc}",
            status_code=500,
        )


@router.post("/filter-discovered", response_model=ScopedMcpFilterVerdictDTO)
async def filter_discovered_mcp_tools(
    agent_id: Annotated[str, Path(..., description="Target agent profile ID")],
    req: ScopedMcpFilterRequestDTO,
    service: Annotated[McpScopeGateService, Depends(get_mcp_scope_gate_service)],
) -> JSONResponse:
    """Filter dynamically discovered candidate tools against the agent's scope policy."""
    try:
        verdict = service.filter_discovered_tools(agent_id, req.candidates)
        return success_response(data=verdict.model_dump())
    except Exception as exc:
        logger.exception("Failed to filter discovered MCP tools for agent %s", agent_id)
        return error_response(
            message=f"Failed to filter discovered MCP tools: {exc}",
            status_code=500,
        )


@router.post("/verify-call", response_model=VerifyToolCallResponseDTO)
async def verify_mcp_tool_invocation(
    agent_id: Annotated[str, Path(..., description="Target agent profile ID")],
    req: VerifyToolCallRequestDTO,
    service: Annotated[McpScopeGateService, Depends(get_mcp_scope_gate_service)],
) -> JSONResponse:
    """Verify whether an agent is authorized to invoke a specific MCP tool (Fail-Closed)."""
    try:
        res = service.verify_tool_call(agent_id, req.server_name, req.tool_name)
        if not res.is_allowed:
            return error_response(
                message=res.reason,
                status_code=403,
            )
        return success_response(data=res.model_dump())
    except Exception as exc:
        logger.exception("Failed to verify tool call for agent %s", agent_id)
        return error_response(
            message=f"Failed to verify tool call: {exc}",
            status_code=500,
        )
