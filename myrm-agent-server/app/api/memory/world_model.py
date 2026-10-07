"""API router for L3 World Model macro memory query and environment sync.

[POS]
app/api/memory/world_model.py
Exposes HTTP endpoints for querying assembled macro context, synchronizing
workspace runtime environments, and updating macro dimensions.

[INPUT]
- fastapi: APIRouter, Depends, Query
- app.schemas.world_model: (WorldModelQueryRequest, WorldModelQueryResponse, WorldModelSyncRequest, ...)
- app.services.memory.world_model: (L3WorldModelService, get_world_model_service)

[OUTPUT]
- router: FastAPI APIRouter mounted under /memory/world-model
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.schemas.world_model import (
    WorldModelFieldsDTO,
    WorldModelQueryRequest,
    WorldModelQueryResponse,
    WorldModelSyncRequest,
    WorldModelSyncResponse,
    WorldModelUpdateRequest,
    WorldModelUpdateResponse,
)
from app.services.memory.world_model import (
    L3WorldModelService,
    get_world_model_service,
)

router = APIRouter(prefix="/world-model", tags=["memory-world-model"])


@router.post(
    "/query",
    response_model=WorldModelQueryResponse,
    summary="Query assembled L3 macro context ready for System Prompt injection",
)
def query_macro_world_model(
    request: WorldModelQueryRequest,
    service: L3WorldModelService = Depends(get_world_model_service),
) -> WorldModelQueryResponse:
    """Retrieve full project macro world model formatted in strict delimiter bounds."""
    return service.query_macro_context(request)


@router.post(
    "/sync",
    response_model=WorldModelSyncResponse,
    summary="Probe workspace runtime profiles and sync into project world model",
)
def sync_workspace_environment(
    request: WorldModelSyncRequest,
    service: L3WorldModelService = Depends(get_world_model_service),
) -> WorldModelSyncResponse:
    """Detect toolchains and config markers in workspace and merge into world model."""
    return service.sync_workspace_environment(request)


@router.post(
    "/update",
    response_model=WorldModelUpdateResponse,
    summary="Update a specific macro dimension directly",
)
def update_macro_dimension(
    request: WorldModelUpdateRequest,
    service: L3WorldModelService = Depends(get_world_model_service),
) -> WorldModelUpdateResponse:
    """Directly mutate safety rules, architecture contract, or domain knowledge."""
    return service.update_dimension(request)


@router.get(
    "/fields",
    response_model=WorldModelFieldsDTO,
    summary="Fetch raw four-dimensional fields of a project world model",
)
def get_world_model_fields(
    project_id: str = Query(default="default", description="Project scope identifier"),
    service: L3WorldModelService = Depends(get_world_model_service),
) -> WorldModelFieldsDTO:
    """Fetch unrendered fields across all four macro dimensions."""
    return service.get_fields(project_id)
