"""FastAPI router for codebase diff volume evaluation and fallback.

[POS]
HTTP boundary for codebase memory large diff fallback, exposing tier evaluation,
numstat parsing, and fail-safe topological synthesis.

[INPUT]
- fastapi::APIRouter, Depends, status
- app.schemas.codebase_diff
- app.services.memory.codebase_diff.provider

[OUTPUT]
- router (FastAPI APIRouter)
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.schemas.codebase_diff import (
    EvaluateDiffRequest,
    EvaluateDiffResponse,
    ParseNumstatRequest,
    ParseNumstatResponse,
)
from app.services.memory.codebase_diff import (
    CodebaseDiffProvider,
    get_codebase_diff_provider,
)

router = APIRouter(prefix="/codebase-diff", tags=["Codebase Diff Fallback"])


@router.post(
    "/evaluate",
    response_model=EvaluateDiffResponse,
    status_code=status.HTTP_200_OK,
    summary="Evaluate diff entries and produce a multi-tiered fallback verdict",
)
async def evaluate_diff(
    request: EvaluateDiffRequest,
    provider: Annotated[CodebaseDiffProvider, Depends(get_codebase_diff_provider)],
) -> EvaluateDiffResponse:
    """Evaluates diff volume against adaptive funnel tiers and returns complete verdict."""
    verdict = provider.evaluate(request)
    return EvaluateDiffResponse(verdict=verdict)


@router.post(
    "/parse-numstat",
    response_model=ParseNumstatResponse,
    status_code=status.HTTP_200_OK,
    summary="Parse raw git numstat text into structured file change entries",
)
async def parse_numstat(
    request: ParseNumstatRequest,
    provider: Annotated[CodebaseDiffProvider, Depends(get_codebase_diff_provider)],
) -> ParseNumstatResponse:
    """Parses standard git diff --numstat lines into categorized entries."""
    entries = provider.parse_numstat(request.numstat_content)
    return ParseNumstatResponse(entries=entries)


@router.get(
    "/health",
    status_code=status.HTTP_200_OK,
    summary="Health check endpoint for codebase diff fallback service",
)
async def health_check() -> dict[str, str]:
    """Simple liveness probe."""
    return {"status": "ok", "service": "codebase_diff"}
