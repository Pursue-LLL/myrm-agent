"""[INPUT]
- app.services.context.omni_reference::OmniReferenceResolverService
- app.services.context.omni_reference::OmniEntityBrief
- app.services.context.omni_reference::ResolvedSliceResult
- fastapi::APIRouter, Query, HTTPException

[OUTPUT]
- omni_reference_router: APIRouter handling 5-dimensional context references search and slice expansion

[POS]
REST API endpoints under /api/v1/context/reference.
Provides real-time search suggestions and bounded slice extraction for chat input @-menu.
"""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.core.utils.response_utils import success_response
from app.schemas.responses import StandardSuccessResponse
from app.services.context.omni_reference import (
    OmniEntityBrief,
    OmniReferenceResolverService,
    ResolvedSliceResult,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/reference", tags=["omni-reference"])

ReferenceDimensionParam = Literal["file", "session", "artifact", "agent", "task"]


class EntityBriefDTO(BaseModel):
    dimension: str
    target_id: str
    label: str
    detail: str | None = None
    icon: str | None = None
    updated_at: str | None = None
    extra: dict[str, str] = {}


class SliceRequestDTO(BaseModel):
    dimension: ReferenceDimensionParam
    target_id: str
    label: str | None = None


class SliceResponseDTO(BaseModel):
    dimension: str
    target_id: str
    label: str
    content_slice: str
    is_truncated: bool
    token_estimate: int
    provenance_uri: str


@router.get("/search", response_model=StandardSuccessResponse)
async def search_reference_entities(
    q: str = Query(default="", description="Search query keyword"),
    dimension: ReferenceDimensionParam | None = Query(default=None, description="Optional dimension filter"),
    limit: int = Query(default=15, ge=1, le=50, description="Max suggestion count"),
) -> StandardSuccessResponse:
    """Search reference entities across 5 dimensions (file, session, artifact, agent, task)."""
    try:
        entities: list[OmniEntityBrief] = await OmniReferenceResolverService.search_entities(
            query=q,
            dimension=dimension,
            limit=limit,
        )

        dtos = [
            EntityBriefDTO(
                dimension=e.dimension,
                target_id=e.target_id,
                label=e.label,
                detail=e.detail,
                icon=e.icon,
                updated_at=e.updated_at,
                extra=e.extra,
            ).model_dump()
            for e in entities
        ]

        return success_response(data=dtos)
    except Exception as e:
        logger.error("Failed to search omni reference entities: %s", e)
        raise HTTPException(status_code=500, detail="Failed to search reference entities") from e


@router.post("/slice", response_model=StandardSuccessResponse)
async def resolve_context_slice(
    request: SliceRequestDTO,
) -> StandardSuccessResponse:
    """Resolve raw content and extract bounded context slice with provenance URI."""
    try:
        result: ResolvedSliceResult = await OmniReferenceResolverService.resolve_slice(
            dimension=request.dimension,
            target_id=request.target_id,
            label=request.label,
        )

        dto = SliceResponseDTO(
            dimension=result.dimension,
            target_id=result.target_id,
            label=result.label,
            content_slice=result.content_slice,
            is_truncated=result.is_truncated,
            token_estimate=result.token_estimate,
            provenance_uri=result.provenance_uri,
        )

        return success_response(data=dto.model_dump())
    except Exception as e:
        logger.error("Failed to resolve context slice for %s:%s: %s", request.dimension, request.target_id, e)
        raise HTTPException(status_code=500, detail="Failed to resolve context slice") from e
