"""
[POS] app/api/memory/client_partition.py
[INPUT] fastapi, app.schemas.memory_client_partition, app.services.memory.memory_client_partition_service
[OUTPUT] router

FastAPI router exposing endpoints for Client-Isolated Workspace and Memory Namespace Partition Suite.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status

from app.schemas.memory_client_partition import (
    ClientPartitionConfigDTO,
    ClientWorkspaceDescriptorDTO,
    ScreenClientMemoriesRequestDTO,
    ScreenClientMemoriesResponseDTO,
)
from app.services.memory.memory_client_partition_service import (
    MemoryClientPartitionService,
    get_memory_client_partition_service,
)

router = APIRouter()


@router.post(
    "/client-partition/workspace/resolve",
    response_model=ClientWorkspaceDescriptorDTO,
    status_code=status.HTTP_200_OK,
    summary="Resolve and isolate a client workspace folder preventing path traversal",
)
def resolve_client_workspace(
    request: ClientPartitionConfigDTO,
    auto_create: bool = Query(default=False, description="Whether to create the folder if not present"),
    service: MemoryClientPartitionService = Depends(get_memory_client_partition_service),
) -> ClientWorkspaceDescriptorDTO:
    """Resolve and validate an isolated workspace folder for target client context."""
    return service.resolve_client_workspace(request, auto_create=auto_create)


@router.post(
    "/client-partition/screen",
    response_model=ScreenClientMemoriesResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="Screen candidate memories and purge any foreign client memories",
)
def screen_client_memories(
    request: ScreenClientMemoriesRequestDTO,
    service: MemoryClientPartitionService = Depends(get_memory_client_partition_service),
) -> ScreenClientMemoriesResponseDTO:
    """Screen candidate memories against active client context to eliminate cross-client leakage."""
    return service.screen_client_memories(request)
