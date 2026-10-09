"""Vector space consistency guard API router.

[POS]
FastAPI endpoints for pre-flight vector space validation, collection space binding,
status diagnostics, and re-indexing workflows.

[INPUT]
- fastapi (APIRouter, Depends, status)
- app.schemas.space_guard (
    SpaceBindRequest,
    SpaceBindResponse,
    SpaceReindexRequest,
    SpaceReindexResponse,
    SpaceStatusResponse,
    SpaceValidateRequest,
    SpaceValidateResponse,
  )
- app.services.memory.space_guard (VectorSpaceGuardService, get_space_guard_service)

[OUTPUT]
- router: APIRouter with /validate, /bind, /status/{collection}, and /reindex endpoints
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.schemas.space_guard import (
    SpaceBindRequest,
    SpaceBindResponse,
    SpaceReindexRequest,
    SpaceReindexResponse,
    SpaceStatusResponse,
    SpaceValidateRequest,
    SpaceValidateResponse,
)
from app.services.memory.space_guard import (
    VectorSpaceGuardService,
    get_space_guard_service,
)

router = APIRouter(prefix="/space-guard", tags=["Memory Vector Space Guard"])


@router.post(
    "/validate",
    response_model=SpaceValidateResponse,
    summary="Validate vector space compatibility before write/search",
    status_code=status.HTTP_200_OK,
)
async def validate_vector_space(
    payload: SpaceValidateRequest,
    service: VectorSpaceGuardService = Depends(get_space_guard_service),
) -> SpaceValidateResponse:
    """Validate runtime model against collection space fingerprint."""
    return await service.validate_space(payload)


@router.post(
    "/bind",
    response_model=SpaceBindResponse,
    summary="Bind or update canonical model fingerprint for collection",
    status_code=status.HTTP_200_OK,
)
async def bind_vector_space(
    payload: SpaceBindRequest,
    service: VectorSpaceGuardService = Depends(get_space_guard_service),
) -> SpaceBindResponse:
    """Bind collection to an embedding model fingerprint."""
    return await service.bind_space(payload)


@router.get(
    "/status/{collection}",
    response_model=SpaceStatusResponse,
    summary="Get collection vector space status and registered fingerprint",
    status_code=status.HTTP_200_OK,
)
async def get_space_status(
    collection: str,
    service: VectorSpaceGuardService = Depends(get_space_guard_service),
) -> SpaceStatusResponse:
    """Retrieve vector space metadata and diagnostic status."""
    return await service.get_space_status(collection)


@router.post(
    "/reindex",
    response_model=SpaceReindexResponse,
    summary="Trigger safe vector space migration and re-indexing",
    status_code=status.HTTP_200_OK,
)
async def reindex_vector_space(
    payload: SpaceReindexRequest,
    service: VectorSpaceGuardService = Depends(get_space_guard_service),
) -> SpaceReindexResponse:
    """Execute space migration and re-indexing."""
    return await service.execute_reindex(payload)
