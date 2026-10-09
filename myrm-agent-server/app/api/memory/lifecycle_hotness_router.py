"""[POS]: app/api/memory/lifecycle_hotness_router.py
[INPUT]: REST API requests for single hotness scoring and batch blended reranking.
[OUTPUT]: FastAPI endpoints exposing memory hotness calculation and lifecycle classification.
"""

from fastapi import APIRouter, Depends

from app.schemas.lifecycle_hotness import (
    BlendRerankRequest,
    BlendRerankResponse,
    SingleScoreRequest,
    SingleScoreResponse,
)
from app.services.memory.lifecycle_hotness_service import (
    LifecycleHotnessService,
    get_lifecycle_hotness_service,
)

router = APIRouter(prefix="/lifecycle-hotness", tags=["Memory - Lifecycle Hotness"])


@router.post("/score", response_model=SingleScoreResponse)
async def score_single(
    request: SingleScoreRequest,
    service: LifecycleHotnessService = Depends(get_lifecycle_hotness_service),
) -> SingleScoreResponse:
    """Compute deterministic hotness score and lifecycle classification for a single entity."""
    return service.score_single(request)


@router.post("/blend-rerank", response_model=BlendRerankResponse)
async def blend_rerank(
    request: BlendRerankRequest,
    service: LifecycleHotnessService = Depends(get_lifecycle_hotness_service),
) -> BlendRerankResponse:
    """Rerank candidate memories by blending semantic similarity with exponential time-decay hotness."""
    return service.blend_rerank(request)
