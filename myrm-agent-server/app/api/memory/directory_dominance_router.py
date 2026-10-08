"""[POS]: app/api/memory/directory_dominance_router.py
[INPUT]: REST API requests for hierarchical retrieval and directory dominance evaluation.
[OUTPUT]: FastAPI endpoints exposing hierarchical directory dominance search capabilities.
"""

from fastapi import APIRouter, Depends

from app.schemas.directory_dominance import (
    DominanceEvaluationRequest,
    DominanceEvaluationResponse,
    HierarchicalRetrieveRequest,
    HierarchicalRetrieveResponse,
)
from app.services.memory.directory_dominance_service import (
    DirectoryDominanceService,
    get_directory_dominance_service,
)

router = APIRouter(prefix="/directory-dominance", tags=["Memory - Directory Dominance"])


@router.post("/retrieve", response_model=HierarchicalRetrieveResponse)
async def retrieve_hierarchical(
    request: HierarchicalRetrieveRequest,
    service: DirectoryDominanceService = Depends(get_directory_dominance_service),
) -> HierarchicalRetrieveResponse:
    """Execute hierarchical directory dominance retrieval with sibling context bundling."""
    return service.retrieve(request)


@router.post("/evaluate-dominance", response_model=DominanceEvaluationResponse)
async def evaluate_dominance(
    request: DominanceEvaluationRequest,
    service: DirectoryDominanceService = Depends(get_directory_dominance_service),
) -> DominanceEvaluationResponse:
    """Evaluate whether a directory node dominates its children based on dominance_ratio."""
    return service.evaluate_dominance(request)
