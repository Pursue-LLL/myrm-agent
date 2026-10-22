"""FastAPI router for SwarmForge Dynamic Topology Orchestrator & Mesh Bus (Item 55).

[INPUT]
- app.schemas.swarm_mesh::{
    CreateTopologyRequest,
    SwitchTopologyRequest,
    ScaleNodesRequest,
    MigrateNodeRequest,
    SendMeshMessageRequest,
    WriteBlackboardRequest,
  }
- app.services.agent.swarm_mesh_service::{
    SwarmMeshService,
    get_swarm_mesh_service,
  }

[OUTPUT]
- REST endpoints under /agents/swarm-mesh for topology retrieval, seamless switching,
  node scaling, live role migration, P2P mesh bus messaging, and shared blackboard.

[POS]
- HTTP API layer for dynamic multi-agent topology orchestration and mesh network communication.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query, status

from app.schemas.responses import StandardSuccessResponse, create_success_response
from app.schemas.swarm_mesh import (
    CreateTopologyRequest,
    MigrateNodeRequest,
    ScaleNodesRequest,
    SendMeshMessageRequest,
    SwitchTopologyRequest,
    WriteBlackboardRequest,
)
from app.services.agent.swarm_mesh_service import SwarmMeshService, get_swarm_mesh_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agents/swarm-mesh", tags=["SwarmForge Dynamic Topology & Mesh"])


@router.get(
    "/topology",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Get current swarm topology state",
)
async def get_topology_state(
    topology_id: str | None = Query(None, description="Optional swarm topology ID"),
    service: SwarmMeshService = Depends(get_swarm_mesh_service),
) -> StandardSuccessResponse:
    """Retrieve active swarm topology nodes, interconnecting edges, blackboard, and messages."""
    state = service.get_topology_state(topology_id)
    return create_success_response(data=state.model_dump())


@router.post(
    "/create",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create or reset dynamic swarm topology",
)
async def create_topology(
    req: CreateTopologyRequest,
    service: SwarmMeshService = Depends(get_swarm_mesh_service),
) -> StandardSuccessResponse:
    """Instantiate a new swarm topology with specified layout and initial nodes."""
    state = service.create_topology(req)
    return create_success_response(data=state.model_dump())


@router.post(
    "/switch",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Seamlessly switch topology layout at runtime",
)
async def switch_topology(
    req: SwitchTopologyRequest,
    topology_id: str | None = Query(None, description="Optional swarm topology ID"),
    service: SwarmMeshService = Depends(get_swarm_mesh_service),
) -> StandardSuccessResponse:
    """Dynamically reconfigure communication edges while preserving node states and blackboard facts."""
    state = service.switch_topology(req, topology_id)
    return create_success_response(data=state.model_dump())


@router.post(
    "/scale",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Scale out or scale in swarm nodes",
)
async def scale_nodes(
    req: ScaleNodesRequest,
    topology_id: str | None = Query(None, description="Optional swarm topology ID"),
    service: SwarmMeshService = Depends(get_swarm_mesh_service),
) -> StandardSuccessResponse:
    """Elastically add a new node or retire an idle node from the active mesh."""
    state = service.scale_nodes(req, topology_id)
    return create_success_response(data=state.model_dump())


@router.post(
    "/migrate",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Live-migrate a node to a different functional role",
)
async def migrate_node(
    req: MigrateNodeRequest,
    topology_id: str | None = Query(None, description="Optional swarm topology ID"),
    service: SwarmMeshService = Depends(get_swarm_mesh_service),
) -> StandardSuccessResponse:
    """Execute live node migration, recalculate peer links, and retain state metadata."""
    result = service.migrate_node(req, topology_id)
    return create_success_response(data=result.model_dump())


@router.post(
    "/messages",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Send message through P2P mesh bus",
)
async def send_mesh_message(
    req: SendMeshMessageRequest,
    topology_id: str | None = Query(None, description="Optional swarm topology ID"),
    service: SwarmMeshService = Depends(get_swarm_mesh_service),
) -> StandardSuccessResponse:
    """Transmit a unicast, multicast, or broadcast message over the mesh event bus."""
    message = service.send_mesh_message(req, topology_id)
    return create_success_response(data=message.model_dump())


@router.get(
    "/blackboard",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Read shared blackboard facts",
)
async def get_blackboard(
    key: str | None = Query(None, description="Optional specific fact key"),
    topology_id: str | None = Query(None, description="Optional swarm topology ID"),
    service: SwarmMeshService = Depends(get_swarm_mesh_service),
) -> StandardSuccessResponse:
    """Fetch all or specific key-value assertions stored in the shared blackboard."""
    facts = service.get_blackboard(key, topology_id)
    return create_success_response(data={k: v.model_dump() for k, v in facts.items()})


@router.post(
    "/blackboard",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Write or update shared blackboard fact",
)
async def write_blackboard(
    req: WriteBlackboardRequest,
    topology_id: str | None = Query(None, description="Optional swarm topology ID"),
    service: SwarmMeshService = Depends(get_swarm_mesh_service),
) -> StandardSuccessResponse:
    """Record or update a shared fact with automatic version incrementing."""
    entry = service.write_blackboard(req, topology_id)
    return create_success_response(data=entry.model_dump())
