"""Memory reindex operations — detect orphan collections and re-embed.

[INPUT]
app.api.memory.utils::get_crud_memory_manager (POS: Memory API utilities)
myrm_agent_harness.toolkits.memory._manager.reindex::{OrphanCollectionInfo, ReindexEstimate, ReindexResult}

[OUTPUT]
router: /reindex endpoints for estimating and executing memory reindex

[POS]
Memory reindex API layer. Exposes orphan detection, estimation, and
reindex execution for the frontend Settings UI and Memory Doctor.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from myrm_agent_harness.toolkits.memory import MemoryManager
from pydantic import BaseModel

from app.api.memory.utils import get_crud_memory_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/reindex")


class OrphanCollectionItem(BaseModel):
    collection_name: str
    memory_type: str
    old_model_suffix: str
    document_count: int


class ReindexEstimateResponse(BaseModel):
    total_memories: int
    orphan_collections: list[OrphanCollectionItem]


class ReindexResultResponse(BaseModel):
    migrated: int
    skipped: int
    failed: int


@router.get("/estimate", response_model=ReindexEstimateResponse)
async def estimate_reindex(
    manager: MemoryManager = Depends(get_crud_memory_manager),
) -> ReindexEstimateResponse:
    """Estimate orphan memories that need re-embedding after a model switch."""
    estimate = await manager.estimate_reindex()
    return ReindexEstimateResponse(
        total_memories=estimate.total_memories,
        orphan_collections=[
            OrphanCollectionItem(
                collection_name=o.collection_name,
                memory_type=o.memory_type,
                old_model_suffix=o.old_model_suffix,
                document_count=o.document_count,
            )
            for o in estimate.orphan_collections
        ],
    )


@router.post("", response_model=ReindexResultResponse)
async def execute_reindex(
    manager: MemoryManager = Depends(get_crud_memory_manager),
) -> ReindexResultResponse:
    """Execute reindex: re-embed orphan memories with the current embedding model.

    Old collections are preserved as a safety net.
    """
    result = await manager.reindex_from_orphans()
    return ReindexResultResponse(
        migrated=result.migrated,
        skipped=result.skipped,
        failed=result.failed,
    )
