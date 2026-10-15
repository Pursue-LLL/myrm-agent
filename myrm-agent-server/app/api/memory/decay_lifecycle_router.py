"""FastAPI router for Ebbinghaus memory decay and tiered storage lifecycle.

[INPUT]
- REST requests for periodic evaluation and revival.

[OUTPUT]
- Endpoints returning evaluation reports and cold archives.

[POS]
- app.api.memory.decay_lifecycle_router
"""

import logging

from fastapi import APIRouter, HTTPException, status

from app.schemas.decay_lifecycle import (
    EvaluateLifecycleRequest,
    EvaluateLifecycleResponse,
    ExportColdArchiveResponse,
    ReviveMemoryRequest,
    ReviveMemoryResponse,
)
from app.services.memory.decay_lifecycle_service import (
    decay_lifecycle_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/lifecycle", tags=["memory-decay-lifecycle"])


@router.post("/evaluate", response_model=EvaluateLifecycleResponse)
async def evaluate_lifecycle_endpoint(
    request: EvaluateLifecycleRequest | None = None,
) -> EvaluateLifecycleResponse:
    """Trigger periodic memory decay evaluation and update hot/warm/cold tier placements."""
    current_time = request.current_time if request else None
    return decay_lifecycle_service.evaluate_and_migrate(current_time=current_time)


@router.post("/revive", response_model=ReviveMemoryResponse)
async def revive_memory_endpoint(
    request: ReviveMemoryRequest,
) -> ReviveMemoryResponse:
    """Reactivate a cold or archived memory, promoting it back to active HOT tier."""
    revived = decay_lifecycle_service.revive_memory(request)
    if not revived:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Memory '{request.memory_id}' not found in lifecycle tracking manager",
        )
    return revived


@router.get("/cold-archive", response_model=ExportColdArchiveResponse)
async def export_cold_archive_endpoint() -> ExportColdArchiveResponse:
    """Export serialized cold archive records for offline storage or backup."""
    return decay_lifecycle_service.export_cold_archive()
