"""FastAPI router for Per-Project Workspace Team Blueprint Auto-Reuse (Item 36).

[INPUT]
- app.schemas.workspace_blueprint::{BindWorkspaceBlueprintRequest, ...}
- app.services.agent.workspace_blueprint_service::{WorkspaceBlueprintService, get_workspace_blueprint_service}

[OUTPUT]
- Router mounted under /workspaces/{workspace_id}/blueprints.

[POS]
- HTTP endpoints for workspace-to-blueprint binding, auto-reuse resolution,
  usage recording, unbinding, and active bindings directory.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Path

from app.schemas.responses import StandardSuccessResponse, create_success_response
from app.schemas.workspace_blueprint import (
    BindWorkspaceBlueprintRequest,
)
from app.services.agent.workspace_blueprint_service import (
    WorkspaceBlueprintService,
    get_workspace_blueprint_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/workspaces/{workspace_id}/blueprints", tags=["Workspace Team Blueprint"])


@router.post(
    "",
    response_model=StandardSuccessResponse,
    summary="Bind or update squad blueprint for a project workspace",
)
def bind_workspace_blueprint_endpoint(
    workspace_id: str = Path(..., min_length=1, description="Unique workspace or project identifier"),
    req: BindWorkspaceBlueprintRequest = ...,
    service: WorkspaceBlueprintService = Depends(get_workspace_blueprint_service),
) -> StandardSuccessResponse:
    """Register persistent link between a workspace and an orchestrated squad blueprint."""
    binding = service.bind_blueprint(workspace_id=workspace_id, req=req)
    return create_success_response(data=binding)


@router.get(
    "/active",
    response_model=StandardSuccessResponse,
    summary="Resolve active team blueprint and auto-reuse disposition for workspace",
)
def resolve_workspace_blueprint_endpoint(
    workspace_id: str = Path(..., min_length=1, description="Unique workspace or project identifier"),
    service: WorkspaceBlueprintService = Depends(get_workspace_blueprint_service),
) -> StandardSuccessResponse:
    """Resolve whether workspace has a bound blueprint ready for auto-reuse or recent recommendation."""
    resolution = service.resolve_blueprint(workspace_id=workspace_id)
    return create_success_response(data=resolution)


@router.post(
    "/record-usage",
    response_model=StandardSuccessResponse,
    summary="Record instantiation or usage of the workspace blueprint",
)
def record_blueprint_usage_endpoint(
    workspace_id: str = Path(..., min_length=1, description="Unique workspace or project identifier"),
    service: WorkspaceBlueprintService = Depends(get_workspace_blueprint_service),
) -> StandardSuccessResponse:
    """Update last-used timestamp and LRU recency tracking for the workspace."""
    success = service.record_usage(workspace_id=workspace_id)
    return create_success_response(data={"recorded": success, "workspace_id": workspace_id})


@router.delete(
    "",
    response_model=StandardSuccessResponse,
    summary="Unbind team blueprint from workspace",
)
def unbind_workspace_blueprint_endpoint(
    workspace_id: str = Path(..., min_length=1, description="Unique workspace or project identifier"),
    service: WorkspaceBlueprintService = Depends(get_workspace_blueprint_service),
) -> StandardSuccessResponse:
    """Remove team blueprint binding from the specified workspace."""
    unbound = service.unbind_blueprint(workspace_id=workspace_id)
    return create_success_response(data={"unbound": unbound, "workspace_id": workspace_id})


@router.get(
    "/all",
    response_model=StandardSuccessResponse,
    summary="List all registered workspace blueprint bindings",
)
def list_workspace_blueprints_endpoint(
    service: WorkspaceBlueprintService = Depends(get_workspace_blueprint_service),
) -> StandardSuccessResponse:
    """List all workspace-to-blueprint links sorted by recency."""
    resp = service.list_bindings()
    return create_success_response(data=resp)
