# [POS]: app/api/memory/mem_cube_router.py
# [INPUT]: fastapi, app.schemas.mem_cube, app.services.memory.mem_cube_service
# [OUTPUT]: router (FastAPI APIRouter for Memory Cube Scoped Isolation & Dynamic Mounting Suite)

"""FastAPI router for Memory Cube Scoped Isolation & Dynamic Mounting Suite (Item 124)."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.schemas.mem_cube import (
    CreateCubeRequestDTO,
    CubeMatrixOverviewDTO,
    CubeQueryRequestDTO,
    CubeQueryResultDTO,
    CubeScopeTypeEnum,
    CubeWriteRequestDTO,
    CubeWriteResultDTO,
    MemoryCubeDTO,
    MountPolicyDTO,
    SetMountPolicyRequestDTO,
)
from app.services.memory.mem_cube_service import (
    MemCubeService,
    get_mem_cube_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cubes", tags=["Memory Cubes"])


@router.post(
    "",
    response_model=MemoryCubeDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new Memory Cube compartment",
)
async def create_cube(
    request: CreateCubeRequestDTO,
    service: Annotated[MemCubeService, Depends(get_mem_cube_service)],
) -> MemoryCubeDTO:
    """Create a scoped memory cube with designated boundary type and permissions."""
    return service.create_cube(request)


@router.get(
    "",
    response_model=list[MemoryCubeDTO],
    summary="List registered Memory Cubes",
)
async def list_cubes(
    service: Annotated[MemCubeService, Depends(get_mem_cube_service)],
    scope_type: Annotated[CubeScopeTypeEnum | None, Query(description="Filter by boundary scope")] = None,
    owner_id: Annotated[str | None, Query(description="Filter by owner ID")] = None,
) -> list[MemoryCubeDTO]:
    """Retrieve all memory cubes matching optional scope or ownership criteria."""
    return service.list_cubes(scope_type=scope_type, owner_id=owner_id)


@router.get(
    "/matrix/overview",
    response_model=CubeMatrixOverviewDTO,
    summary="Get global memory cube topology and matrix overview",
)
async def get_matrix_overview(
    service: Annotated[MemCubeService, Depends(get_mem_cube_service)],
) -> CubeMatrixOverviewDTO:
    """Return platform overview of all registered cubes, mount policies, and metrics."""
    return service.get_matrix_overview()


@router.get(
    "/{cube_id}",
    response_model=MemoryCubeDTO,
    summary="Get a specific Memory Cube by ID",
)
async def get_cube(
    cube_id: str,
    service: Annotated[MemCubeService, Depends(get_mem_cube_service)],
) -> MemoryCubeDTO:
    """Retrieve metadata of a single memory cube."""
    cube = service.get_cube(cube_id)
    if not cube:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Memory cube '{cube_id}' not found.",
        )
    return cube


@router.delete(
    "/{cube_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an existing Memory Cube",
)
async def delete_cube(
    cube_id: str,
    service: Annotated[MemCubeService, Depends(get_mem_cube_service)],
) -> None:
    """Remove a memory cube compartment."""
    success = service.delete_cube(cube_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Memory cube '{cube_id}' not found.",
        )


@router.post(
    "/mount/{agent_id}",
    response_model=MountPolicyDTO,
    summary="Configure dynamic mount policy for an agent",
)
async def set_mount_policy(
    agent_id: str,
    request: SetMountPolicyRequestDTO,
    service: Annotated[MemCubeService, Depends(get_mem_cube_service)],
) -> MountPolicyDTO:
    """Establish decoupled read/write permissions and dynamic mounting topology for an agent."""
    return service.set_mount_policy(agent_id, request)


@router.get(
    "/mount/{agent_id}",
    response_model=MountPolicyDTO,
    summary="Retrieve active mount policy for an agent",
)
async def get_mount_policy(
    agent_id: str,
    service: Annotated[MemCubeService, Depends(get_mem_cube_service)],
) -> MountPolicyDTO:
    """Inspect the current readable and writable cube bindings for an agent."""
    policy = service.get_mount_policy(agent_id)
    if not policy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Mount policy for agent '{agent_id}' not found.",
        )
    return policy


@router.post(
    "/write",
    response_model=CubeWriteResultDTO,
    summary="Write memory record routed through dynamic mount policy",
)
async def write_to_cube(
    request: CubeWriteRequestDTO,
    service: Annotated[MemCubeService, Depends(get_mem_cube_service)],
) -> CubeWriteResultDTO:
    """Route memory write through agent's mount policy, rejecting unauthorized mutations."""
    return service.write_record(request)


@router.post(
    "/query",
    response_model=CubeQueryResultDTO,
    summary="Execute federated search across mounted readable cubes",
)
async def query_cubes(
    request: CubeQueryRequestDTO,
    service: Annotated[MemCubeService, Depends(get_mem_cube_service)],
) -> CubeQueryResultDTO:
    """Perform aggregated query across all cubes mounted as readable by the querying agent."""
    return service.query_cubes(request)
