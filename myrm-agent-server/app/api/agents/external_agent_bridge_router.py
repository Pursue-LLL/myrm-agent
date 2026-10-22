"""[INPUT] ExternalAgentBridgeService, schemas/external_agent_bridge.py.
[OUTPUT] StandardSuccessResponse containing external agent configs, probe results, or receipts.
[POS] FastAPI router for Heterogeneous External Agent Bridge & CLI Adapter endpoints.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from app.schemas.external_agent_bridge import (
    OperationStatusResponse,
    ProcessExecutionRequestDTO,
    RegisterExternalAgentRequest,
)
from app.schemas.responses import StandardSuccessResponse, create_success_response
from app.services.agent.external_agent_bridge_service import ExternalAgentBridgeService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agents/external-bridge", tags=["External Agent Bridge"])


def get_external_agent_bridge_service() -> ExternalAgentBridgeService:
    """Dependency injector for ExternalAgentBridgeService singleton."""
    return ExternalAgentBridgeService.get_instance()


@router.get(
    "/agents",
    response_model=StandardSuccessResponse,
    summary="List all registered external CLI agents",
)
def list_external_agents_endpoint(
    service: ExternalAgentBridgeService = Depends(get_external_agent_bridge_service),
) -> StandardSuccessResponse:
    """Retrieve all external CLI agent configurations."""
    result = service.list_agents()
    return create_success_response(data=result)


@router.post(
    "/agents",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register or update an external CLI agent",
)
def register_external_agent_endpoint(
    req: RegisterExternalAgentRequest,
    service: ExternalAgentBridgeService = Depends(get_external_agent_bridge_service),
) -> StandardSuccessResponse:
    """Register a new external CLI agent process profile."""
    config = service.register_agent(req)
    return create_success_response(data=config)


@router.get(
    "/agents/{agent_id}",
    response_model=StandardSuccessResponse,
    summary="Get configuration of an external CLI agent",
)
def get_external_agent_endpoint(
    agent_id: str,
    service: ExternalAgentBridgeService = Depends(get_external_agent_bridge_service),
) -> StandardSuccessResponse:
    """Fetch profile of a specific external CLI agent."""
    config = service.get_agent(agent_id)
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"External agent {agent_id} not found",
        )
    return create_success_response(data=config)


@router.delete(
    "/agents/{agent_id}",
    response_model=StandardSuccessResponse,
    summary="Unregister an external CLI agent",
)
def unregister_external_agent_endpoint(
    agent_id: str,
    service: ExternalAgentBridgeService = Depends(get_external_agent_bridge_service),
) -> StandardSuccessResponse:
    """Remove an external CLI agent configuration."""
    success = service.unregister_agent(agent_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"External agent {agent_id} not found",
        )
    return create_success_response(
        data=OperationStatusResponse(
            success=True,
            action="unregistered",
            detail=f"Agent {agent_id} unregistered successfully",
        )
    )


@router.get(
    "/agents/{agent_id}/probe",
    response_model=StandardSuccessResponse,
    summary="Probe health and executable availability of external CLI agent",
)
def probe_external_agent_endpoint(
    agent_id: str,
    service: ExternalAgentBridgeService = Depends(get_external_agent_bridge_service),
) -> StandardSuccessResponse:
    """Check whether configured binary command exists in PATH and is executable."""
    probe = service.probe_agent(agent_id)
    if not probe:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"External agent {agent_id} not found",
        )
    return create_success_response(data=probe)


@router.post(
    "/agents/{agent_id}/execute",
    response_model=StandardSuccessResponse,
    summary="Execute a task synchronously via external CLI agent",
)
def execute_external_agent_task_endpoint(
    agent_id: str,
    req: ProcessExecutionRequestDTO,
    service: ExternalAgentBridgeService = Depends(get_external_agent_bridge_service),
) -> StandardSuccessResponse:
    """Dispatch execution task to external CLI agent and return verifiable receipt."""
    if not service.get_agent(agent_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"External agent {agent_id} not found",
        )
    receipt = service.execute_task(agent_id, req)
    return create_success_response(data=receipt)


@router.get(
    "/agents/{agent_id}/receipts",
    response_model=StandardSuccessResponse,
    summary="Get execution receipts history for external CLI agent",
)
def get_external_agent_receipts_endpoint(
    agent_id: str,
    service: ExternalAgentBridgeService = Depends(get_external_agent_bridge_service),
) -> StandardSuccessResponse:
    """Retrieve historical receipts generated by this agent."""
    history = service.get_receipts(agent_id)
    if not history:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"External agent {agent_id} not found",
        )
    return create_success_response(data=history)
