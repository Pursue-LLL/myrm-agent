"""FastAPI router for multimodal vision assets and sandbox artifacts memory endpoints.

[INPUT]
- app.schemas.multimodal_memory
- app.services.memory.multimodal_memory_service

[OUTPUT]
- router: APIRouter with multimodal ingestion and cross-modal search routes

[POS]
app.api.memory.multimodal_memory_router
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.schemas.multimodal_memory import (
    MultimodalIngestRequestDTO,
    MultimodalMemoryItemDTO,
    MultimodalSearchRequestDTO,
    MultimodalSearchResponseDTO,
)
from app.services.memory.multimodal_memory_service import (
    multimodal_memory_service,
)

router = APIRouter(prefix="/multimodal", tags=["Multimodal Vision & Artifact Memory"])


@router.post(
    "/ingest",
    response_model=MultimodalMemoryItemDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest a vision asset or sandbox artifact into multimodal memory",
)
async def ingest_multimodal_asset_endpoint(
    payload: MultimodalIngestRequestDTO,
) -> MultimodalMemoryItemDTO:
    """Ingest, extract features, and index a vision asset or sandbox artifact."""
    return multimodal_memory_service.ingest_asset(payload)


@router.post(
    "/search",
    response_model=MultimodalSearchResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="Perform cross-modal semantic search against stored vision assets and artifacts",
)
async def search_multimodal_assets_endpoint(
    payload: MultimodalSearchRequestDTO,
) -> MultimodalSearchResponseDTO:
    """Execute cross-modal search with optional modality and artifact kind filters."""
    return multimodal_memory_service.search_assets(payload)


@router.get(
    "/items/{item_id}",
    response_model=MultimodalMemoryItemDTO,
    status_code=status.HTTP_200_OK,
    summary="Retrieve a stored multimodal memory item by ID",
)
async def get_multimodal_item_endpoint(
    item_id: str,
) -> MultimodalMemoryItemDTO:
    """Retrieve full domain item metadata for a specific multimodal item."""
    item = multimodal_memory_service.get_asset(item_id)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Multimodal memory item '{item_id}' not found",
        )
    return item


@router.get(
    "/items/{item_id}/card",
    status_code=status.HTTP_200_OK,
    summary="Retrieve UI presentation card for a multimodal item",
)
async def get_multimodal_card_endpoint(
    item_id: str,
) -> dict[str, str]:
    """Retrieve UI card projection attributes for rendering an artifact card."""
    card = multimodal_memory_service.get_asset_card(item_id)
    if card is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Multimodal item '{item_id}' not found",
        )
    return card


@router.get(
    "/health",
    status_code=status.HTTP_200_OK,
    summary="Health check for multimodal memory subsystem",
)
async def multimodal_memory_health() -> dict[str, str]:
    """Return health status of the multimodal memory subsystem."""
    return {"status": "ok", "subsystem": "multimodal_vision_and_artifact_memory"}
