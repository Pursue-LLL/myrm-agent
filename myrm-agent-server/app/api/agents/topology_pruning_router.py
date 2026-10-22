"""REST API endpoints for Model-Tier Adaptive Topology Pruning and folding evaluation.

[INPUT]
- fastapi::APIRouter, status
- app.services.agent.topology_pruning_service::(
    ModelTierCatalogResponse,
    PruneEvaluationRequest,
    PruneEvaluationResponse,
    TopologyPruningService,
  )

[OUTPUT]
- POST /api/v1/agents/topology/prune-evaluation: Evaluate topology pruning recommendation for a task.
- GET /api/v1/agents/topology/tiers: Retrieve model intelligence tier hierarchy and guidelines.

[POS]
REST API surface enabling client UIs to display adaptive folding status and tokens/turns savings.
"""

from __future__ import annotations

from fastapi import APIRouter, status

from app.services.agent.topology_pruning_service import (
    ModelTierCatalogResponse,
    PruneEvaluationRequest,
    PruneEvaluationResponse,
    TopologyPruningService,
)

router = APIRouter(prefix="/agents/topology", tags=["Topology Pruning"])
_service = TopologyPruningService()


@router.post(
    "/prune-evaluation",
    response_model=PruneEvaluationResponse,
    status_code=status.HTTP_200_OK,
    summary="Evaluate model-tier adaptive topology pruning for a task",
)
async def evaluate_topology_pruning(
    request: PruneEvaluationRequest,
) -> PruneEvaluationResponse:
    """Assess whether multi-agent subtasks should be folded into direct single-agent reasoning."""
    return _service.evaluate_pruning(request)


@router.get(
    "/tiers",
    response_model=ModelTierCatalogResponse,
    status_code=status.HTTP_200_OK,
    summary="List model intelligence tiers and pruning recommendations",
)
async def get_model_tier_catalog() -> ModelTierCatalogResponse:
    """Retrieve all supported model intelligence tiers and their representative models."""
    return _service.get_tier_catalog()
