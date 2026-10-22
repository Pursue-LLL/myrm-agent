"""[INPUT] AgentRegisterRequest, RecordErrorRequest, ResolveCapabilityRequest, and session query params.
[OUTPUT] StandardSuccessResponse containing roster, capability resolution, or isolated errors.
[POS] FastAPI router for Agent-Owned multi-agent operations fabric.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.schemas.agent_operations import (
    AgentRegisterRequest,
    RecordErrorRequest,
    ResolveCapabilityRequest,
)
from app.schemas.responses import StandardSuccessResponse, create_success_response
from app.services.agent.agent_operations_service import (
    AgentOperationsService,
    get_agent_operations_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agents/operations", tags=["Agent Operations Fabric"])


@router.post(
    "/register",
    response_model=StandardSuccessResponse,
    summary="Register agent-owned execution context",
)
def register_agent_endpoint(
    req: AgentRegisterRequest,
    service: AgentOperationsService = Depends(get_agent_operations_service),
) -> StandardSuccessResponse:
    """Register an agent instance with owned provider configuration, capabilities, and allowlist."""
    entry = service.register_agent(req)
    return create_success_response(data=entry)


@router.get(
    "/roster",
    response_model=StandardSuccessResponse,
    summary="Fetch list-form agent roster",
)
def get_roster_endpoint(
    session_id: Optional[str] = Query(default=None, description="Optional session filter"),
    service: AgentOperationsService = Depends(get_agent_operations_service),
) -> StandardSuccessResponse:
    """Fetch all registered agents in standardized list-form roster representation."""
    roster = service.get_roster(session_id=session_id)
    return create_success_response(data=roster)


@router.get(
    "/{agent_id}/errors",
    response_model=StandardSuccessResponse,
    summary="Fetch isolated error stack for an agent",
)
def get_agent_errors_endpoint(
    agent_id: str,
    session_id: Optional[str] = Query(default=None, description="Optional session context"),
    service: AgentOperationsService = Depends(get_agent_operations_service),
) -> StandardSuccessResponse:
    """Retrieve isolated errors owned strictly by the specified agent."""
    errors = service.get_agent_errors(agent_id=agent_id, session_id=session_id)
    return create_success_response(data=errors)


@router.post(
    "/{agent_id}/resolve-capability",
    response_model=StandardSuccessResponse,
    summary="Resolve capability alignment against agent-owned allowlist",
)
def resolve_capability_endpoint(
    agent_id: str,
    req: ResolveCapabilityRequest,
    session_id: Optional[str] = Query(default=None, description="Optional session context"),
    service: AgentOperationsService = Depends(get_agent_operations_service),
) -> StandardSuccessResponse:
    """Test whether target capability is allowed under the agent's owned allowlist."""
    res = service.resolve_capability(
        agent_id=agent_id,
        target_capability=req.target_capability,
        session_id=session_id,
    )
    return create_success_response(data=res)


@router.post(
    "/{agent_id}/record-error",
    response_model=StandardSuccessResponse,
    summary="Record isolated error into agent stack",
)
def record_error_endpoint(
    agent_id: str,
    req: RecordErrorRequest,
    session_id: Optional[str] = Query(default=None, description="Optional session context"),
    service: AgentOperationsService = Depends(get_agent_operations_service),
) -> StandardSuccessResponse:
    """Record an operational error strictly within the agent's isolated error stack."""
    scoped_err = service.record_error(agent_id=agent_id, req=req, session_id=session_id)
    return create_success_response(data=scoped_err)


@router.delete(
    "/{agent_id}/errors",
    response_model=StandardSuccessResponse,
    summary="Clear isolated errors for an agent",
)
def clear_agent_errors_endpoint(
    agent_id: str,
    session_id: Optional[str] = Query(default=None, description="Optional session context"),
    service: AgentOperationsService = Depends(get_agent_operations_service),
) -> StandardSuccessResponse:
    """Clear error stack for the target agent."""
    service.clear_agent_errors(agent_id=agent_id, session_id=session_id)
    return create_success_response(data={"cleared": True})
