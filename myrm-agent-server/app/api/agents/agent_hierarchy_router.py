"""
[POS] app/api/agents/agent_hierarchy_router.py
[INPUT] fastapi, app.schemas.agent_hierarchy, app.services.agent.agent_hierarchy_service
[OUTPUT] router

FastAPI router exposing agent creation hierarchy trees, roster tree listings, and provenance ancestry.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.schemas.agent_hierarchy import (
    AgentHierarchyTreeResponseDTO,
    AgentProvenanceDTO,
    RegisterProvenanceRequestDTO,
)
from app.services.agent.agent_hierarchy_service import (
    AgentHierarchyService,
    get_agent_hierarchy_service,
)

router = APIRouter()


@router.get(
    "/hierarchy/tree",
    response_model=AgentHierarchyTreeResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="Get full hierarchical tree listing of agents and sub-agents",
)
def get_agent_hierarchy_tree(
    service: AgentHierarchyService = Depends(get_agent_hierarchy_service),
) -> AgentHierarchyTreeResponseDTO:
    """Retrieve full creation hierarchy tree with parental links and nesting depth."""
    return service.build_tree()


@router.get(
    "/hierarchy/{agent_id}/provenance",
    response_model=AgentProvenanceDTO,
    status_code=status.HTTP_200_OK,
    summary="Get creation provenance details and ancestry path for a specific agent",
)
def get_agent_provenance(
    agent_id: str,
    service: AgentHierarchyService = Depends(get_agent_hierarchy_service),
) -> AgentProvenanceDTO:
    """Fetch creation origin (user, parent agent, script) and ancestor path."""
    prov = service.get_provenance(agent_id)
    if prov is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provenance metadata for agent '{agent_id}' was not found.",
        )
    return prov


@router.post(
    "/hierarchy/provenance",
    response_model=AgentProvenanceDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Register or update agent creation provenance metadata",
)
def register_agent_provenance(
    request: RegisterProvenanceRequestDTO,
    service: AgentHierarchyService = Depends(get_agent_hierarchy_service),
) -> AgentProvenanceDTO:
    """Record creation lineage, creator ID, and parent agent relationship."""
    return service.register_provenance(request)
