"""
[POS] app/api/memory/vector_preflight_router.py
[INPUT] fastapi, app.schemas.memory_vector_preflight, app.services.memory.memory_vector_preflight_service
[OUTPUT] router

FastAPI router exposing endpoints for Vector Store Preflight Dimension Integrity and IPv4 Loopback Sanitizer.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.schemas.memory_vector_preflight import (
    DimensionIntegrityReportDTO,
    InspectVectorStoreRequestDTO,
    InspectVectorStoreResponseDTO,
    SanitizeEndpointRequestDTO,
    SanitizeEndpointResponseDTO,
    VerifyDimensionsRequestDTO,
)
from app.services.memory.memory_vector_preflight_service import (
    MemoryVectorPreflightService,
    get_memory_vector_preflight_service,
)

router = APIRouter()


@router.post(
    "/vector-preflight/sanitize-endpoint",
    response_model=SanitizeEndpointResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="Normalize host and sanitize IPv6 localhost resolution traps to IPv4 127.0.0.1",
)
def sanitize_endpoint(
    request: SanitizeEndpointRequestDTO,
    service: MemoryVectorPreflightService = Depends(get_memory_vector_preflight_service),
) -> SanitizeEndpointResponseDTO:
    """Sanitize endpoint string to eliminate IPv6 ::1 container connection 503/timeout failures."""
    return service.sanitize_endpoint(request)


@router.post(
    "/vector-preflight/verify-dimensions",
    response_model=DimensionIntegrityReportDTO,
    status_code=status.HTTP_200_OK,
    summary="Rigid preflight assertion of embedding dimension compatibility with collection",
)
def verify_dimensions(
    request: VerifyDimensionsRequestDTO,
    service: MemoryVectorPreflightService = Depends(get_memory_vector_preflight_service),
) -> DimensionIntegrityReportDTO:
    """Compare embedding output dimensions against expected collection schema and provide remediation advice."""
    return service.verify_dimensions(request)


@router.post(
    "/vector-preflight/inspect",
    response_model=InspectVectorStoreResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="Composite preflight health check for vector store connection and dimensions",
)
def inspect_vector_store(
    request: InspectVectorStoreRequestDTO,
    service: MemoryVectorPreflightService = Depends(get_memory_vector_preflight_service),
) -> InspectVectorStoreResponseDTO:
    """Execute both endpoint loopback normalization and embedding dimension verification in one preflight pass."""
    return service.inspect_vector_store(request)
