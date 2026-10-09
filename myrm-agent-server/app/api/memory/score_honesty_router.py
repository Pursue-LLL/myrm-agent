"""FastAPI router for retrieval score honesty and raw vs ranking evaluation.

[POS]
HTTP boundary for retrieval score honesty, exposing dual-threshold evaluation,
admitted filtering, and diagnostic statistics.

[INPUT]
- fastapi::APIRouter, Depends
- app.schemas.score_honesty
- app.services.memory.score_honesty.provider

[OUTPUT]
- router (FastAPI APIRouter)
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.schemas.score_honesty import (
    EvaluateCandidatesRequest,
    EvaluateCandidatesResponse,
    FilterCandidatesResponse,
    ScoreHonestyStatsDTO,
)
from app.services.memory.score_honesty import (
    ScoreHonestyProvider,
    get_score_honesty_provider,
)

router = APIRouter(prefix="/score-honesty", tags=["Score Honesty"])


@router.post(
    "/evaluate",
    response_model=EvaluateCandidatesResponse,
    status_code=status.HTTP_200_OK,
    summary="Evaluate search candidates with dual-threshold gates and score breakdowns",
)
async def evaluate_candidates(
    request: EvaluateCandidatesRequest,
    provider: Annotated[ScoreHonestyProvider, Depends(get_score_honesty_provider)],
) -> EvaluateCandidatesResponse:
    """Run dual-threshold evaluation on candidate memories and produce full attribution."""
    evaluated, stats = provider.evaluate(request.candidates, request.config)
    return EvaluateCandidatesResponse(evaluated=evaluated, stats=stats)


@router.post(
    "/filter",
    response_model=FilterCandidatesResponse,
    status_code=status.HTTP_200_OK,
    summary="Filter search candidates, returning only those admitted by dual thresholds",
)
async def filter_candidates(
    request: EvaluateCandidatesRequest,
    provider: Annotated[ScoreHonestyProvider, Depends(get_score_honesty_provider)],
) -> FilterCandidatesResponse:
    """Filter candidates and return admitted list."""
    admitted = provider.filter_admitted(request.candidates, request.config)
    return FilterCandidatesResponse(admitted=admitted, total_admitted=len(admitted))


@router.get(
    "/stats",
    response_model=ScoreHonestyStatsDTO,
    status_code=status.HTTP_200_OK,
    summary="Retrieve aggregate statistics and divergence metrics for score honesty",
)
async def get_stats(
    provider: Annotated[ScoreHonestyProvider, Depends(get_score_honesty_provider)],
) -> ScoreHonestyStatsDTO:
    """Return latest diagnostic statistics."""
    return provider.get_stats()


@router.get(
    "/health",
    status_code=status.HTTP_200_OK,
    summary="Health check endpoint for score honesty service",
)
async def health_check() -> dict[str, str]:
    """Simple liveness probe."""
    return {"status": "ok", "service": "score_honesty"}
