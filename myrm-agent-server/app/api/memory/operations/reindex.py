"""Memory reindex operations — detect orphan collections and re-embed.

[INPUT]
app.api.memory.utils::get_crud_memory_manager (POS: Memory API utilities)
app.services.memory.reindex_run (POS: background run + single flight + polled state)

[OUTPUT]
router: /reindex endpoints — GET /estimate, POST "" (202 starts or joins the run; 409 while a run into another model is in flight) and GET /status

[POS]
Memory reindex API layer for the frontend Settings UI. Re-embedding goes through the user's embedding
provider and can outlast a request, so POST only starts (or joins) the run and the page follows it
through the status route.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from myrm_agent_harness.toolkits.memory import MemoryManager
from pydantic import BaseModel

from app.api.memory.utils import get_crud_memory_manager
from app.services.memory.reindex_run import (
    ReindexBusyError,
    ReindexRun,
    get_memory_reindex_run,
    schedule_memory_reindex,
)

router = APIRouter(prefix="/reindex")


class ReindexEstimateResponse(BaseModel):
    total_memories: int


class ReindexResultResponse(BaseModel):
    migrated: int
    skipped: int
    failed: int


class ReindexStatusResponse(BaseModel):
    state: Literal["idle", "running", "succeeded", "failed"] = "idle"
    done: int = 0
    total: int = 0
    result: ReindexResultResponse | None = None


def _status_response(run: ReindexRun | None) -> ReindexStatusResponse:
    if run is None:
        return ReindexStatusResponse()
    return ReindexStatusResponse(
        state=run.state.value,
        done=run.done,
        total=run.total,
        result=(
            ReindexResultResponse(
                migrated=run.result.migrated,
                skipped=run.result.skipped,
                failed=run.result.failed,
            )
            if run.result is not None
            else None
        ),
    )


@router.get("/estimate", response_model=ReindexEstimateResponse)
async def estimate_reindex(
    manager: MemoryManager = Depends(get_crud_memory_manager),
) -> ReindexEstimateResponse:
    """Estimate orphan memories that need re-embedding after a model switch."""
    estimate = await manager.estimate_reindex()
    return ReindexEstimateResponse(total_memories=estimate.total_memories)


@router.post("", response_model=ReindexStatusResponse, status_code=202)
async def execute_reindex(
    manager: MemoryManager = Depends(get_crud_memory_manager),
) -> ReindexStatusResponse:
    """Start re-embedding orphan memories with the current model in the background, or join the run in flight.

    A memory leaves its old collection only after the current one is read back to hold it, and an emptied
    old collection is dropped. A run into another embedding model that has not finished yet answers 409,
    because joining it would not move anything into the model now in use.
    """
    try:
        return _status_response(schedule_memory_reindex(manager))
    except ReindexBusyError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e


@router.get("/status", response_model=ReindexStatusResponse)
async def get_reindex_status() -> ReindexStatusResponse:
    """Progress of the latest reindex run, with its outcome once it has finished."""
    return _status_response(get_memory_reindex_run())
