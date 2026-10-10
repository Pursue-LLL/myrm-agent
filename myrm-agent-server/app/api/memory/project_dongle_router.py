"""API router for Project Context USB Dongle and cross-agent relay protocol.

[INPUT]
- Workspace paths, DongleBlockDTO items, DTO requests.

[OUTPUT]
- Endpoints for initializing dongle, inspecting state, getting prompt context, and syncing blocks.

[POS]
- Server-side API router for Item 152 ProjectContextUsbDongleAndCrossAgentRelaySuite.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.schemas.project_dongle import (
    DongleContextPromptResponseDTO,
    DongleInitRequestDTO,
    DongleInitResponseDTO,
    DongleStateDTO,
    DongleSyncRequestDTO,
    DongleSyncResponseDTO,
)
from app.services.memory.project_dongle_service import ProjectDongleService

router = APIRouter(prefix="/dongle", tags=["project_dongle"])


def get_dongle_service() -> ProjectDongleService:
    """Dependency provider for ProjectDongleService."""
    return ProjectDongleService()


@router.post("/init", response_model=DongleInitResponseDTO)
def init_project_dongle(
    payload: DongleInitRequestDTO,
    service: ProjectDongleService = Depends(get_dongle_service),
) -> DongleInitResponseDTO:
    """Initialize four standard memory files in the given workspace."""
    return service.init_workspace(payload.workspace_dir)


@router.get("/state", response_model=DongleStateDTO)
def get_dongle_state(
    workspace_dir: str = Query(..., description="Target workspace root directory"),
    service: ProjectDongleService = Depends(get_dongle_service),
) -> DongleStateDTO:
    """Retrieve full four-tier memory state from workspace."""
    return service.get_state(workspace_dir)


@router.get("/prompt", response_model=DongleContextPromptResponseDTO)
def get_dongle_prompt_context(
    workspace_dir: str = Query(..., description="Target workspace root directory"),
    service: ProjectDongleService = Depends(get_dongle_service),
) -> DongleContextPromptResponseDTO:
    """Render deterministic Layer 1 prompt text for cross-agent relay."""
    return service.get_context_prompt(workspace_dir)


@router.post("/sync", response_model=DongleSyncResponseDTO)
def sync_project_dongle_blocks(
    payload: DongleSyncRequestDTO,
    service: ProjectDongleService = Depends(get_dongle_service),
) -> DongleSyncResponseDTO:
    """Batch synchronize memory blocks with automatic overflow archive spilling."""
    return service.sync_blocks(payload.workspace_dir, payload.blocks)
