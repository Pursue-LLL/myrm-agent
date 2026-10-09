"""FastAPI router for CJK iteration mark disambiguation and recall matching.

[POS]
HTTP boundary for ideographic iteration mark ('々') resolution, three-dimensional
token set generation, and bidirectional memory recall matching.

[INPUT]
- fastapi::APIRouter, Depends, status
- app.schemas.cjk_iteration
- app.services.memory.cjk_iteration

[OUTPUT]
- router (FastAPI APIRouter)
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.schemas.cjk_iteration import (
    CjkIterationHealthResponse,
    DisambiguateCjkRequest,
    DisambiguateCjkResponse,
    MatchCjkRecallRequest,
    MatchCjkRecallResponse,
)
from app.services.memory.cjk_iteration import (
    CjkIterationServiceProvider,
    get_cjk_iteration_service_provider,
)

router = APIRouter(prefix="/cjk-iteration", tags=["CJK Iteration Mark"])


@router.post(
    "/disambiguate",
    response_model=DisambiguateCjkResponse,
    status_code=status.HTTP_200_OK,
    summary="Disambiguate CJK iteration marks into normalized text and 3D token matrix",
)
async def disambiguate_cjk_text(
    request: DisambiguateCjkRequest,
    provider: Annotated[
        CjkIterationServiceProvider,
        Depends(get_cjk_iteration_service_provider),
    ],
) -> DisambiguateCjkResponse:
    """Expands '々' ideographs following valid antecedent rules and computes token sets."""
    return provider.disambiguate(request)


@router.post(
    "/match",
    response_model=MatchCjkRecallResponse,
    status_code=status.HTTP_200_OK,
    summary="Calculate bidirectional recall match score between query and memory text",
)
async def match_cjk_recall(
    request: MatchCjkRecallRequest,
    provider: Annotated[
        CjkIterationServiceProvider,
        Depends(get_cjk_iteration_service_provider),
    ],
) -> MatchCjkRecallResponse:
    """Matches query against memory item taking surface and normalized iteration marks into account."""
    return provider.match(request)


@router.get(
    "/health",
    response_model=CjkIterationHealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Health check endpoint for CJK iteration mark subsystem",
)
async def cjk_iteration_health() -> CjkIterationHealthResponse:
    """Returns operational health status of CJK iteration mark subsystem."""
    return CjkIterationHealthResponse()
