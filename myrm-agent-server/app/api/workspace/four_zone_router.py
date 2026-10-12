"""REST API for Four-Zone Workspace Layout and Read-Only Source Protection.

[INPUT]
- DTO schemas from app.schemas.four_zone
- FourZoneService from app.services.workspace.four_zone_service

[OUTPUT]
- APIRouter mounted under /workspace/four-zone

[POS]
Server API. Exposes endpoints for initializing the four zones, evaluating file operation
permissions, replicating raw documents to drafts, and promoting approved artifacts forward.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter

from app.schemas.four_zone import (
    FourZoneCheckRequest,
    FourZoneCheckResponse,
    FourZoneInitRequest,
    FourZoneInitResponse,
    FourZonePromotionRequest,
    FourZonePromotionResponse,
    FourZoneReplicateRequest,
    FourZoneReplicateResponse,
)
from app.services.workspace.four_zone_service import get_four_zone_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/four-zone", tags=["workspace-four-zone"])


@router.post(
    "/scaffold",
    response_model=FourZoneInitResponse,
    summary="Initialize four-zone directory layout with metadata manifests",
)
async def initialize_four_zone_workspace(
    body: FourZoneInitRequest,
) -> FourZoneInitResponse:
    """Create standard 4-zone directory topology (01_原始材料, 02_过程草稿, 03_内容底稿, 04_交付成果)."""
    service = get_four_zone_service()
    return service.initialize_workspace(body)


@router.post(
    "/check",
    response_model=FourZoneCheckResponse,
    summary="Validate file operation permissions against zone invariant policies",
)
async def check_zone_operation(
    body: FourZoneCheckRequest,
) -> FourZoneCheckResponse:
    """Assert whether a write, delete, or rename operation is allowed on the target path."""
    service = get_four_zone_service()
    return service.check_operation(body)


@router.post(
    "/replicate",
    response_model=FourZoneReplicateResponse,
    summary="Safely copy a raw file from Zone 01 into Zone 02 draft",
)
async def replicate_to_draft(
    body: FourZoneReplicateRequest,
) -> FourZoneReplicateResponse:
    """Duplicate protected original file from 01_原始材料 into 02_过程草稿 for editing."""
    service = get_four_zone_service()
    return service.replicate_to_draft(body)


@router.post(
    "/promote",
    response_model=FourZonePromotionResponse,
    summary="Promote artifact forward across workspace zones",
)
async def promote_artifact(
    body: FourZonePromotionRequest,
) -> FourZonePromotionResponse:
    """Advance an approved draft to canonical blueprint, or canonical blueprint to deliverable."""
    service = get_four_zone_service()
    return service.promote(body)
