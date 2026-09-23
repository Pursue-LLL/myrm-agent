"""Wiki Writeback and 5-Layer structure REST routes.

[INPUT]
- fastapi::APIRouter, Depends, Query, HTTPException
- app.services.wiki.writeback
- app.services.wiki.vault::resolve_wiki_vault_path
- myrm_agent_harness.toolkits.wiki.core.structure::WikiStructure

[OUTPUT]
- router (Writeback sub-router)

[POS]
REST API endpoints for task usage ledger recording, review slip generation,
and 5-layer structure stats inspection.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, Query
from myrm_agent_harness.toolkits.wiki.core.structure import WikiStructure
from pydantic import BaseModel, Field

from app.api.dependencies import get_workspace_root
from app.services.wiki.vault import resolve_wiki_vault_path
from app.services.wiki.writeback import (
    ReviewSlipBatch,
    UsageLedgerRecord,
    WikiLayerItem,
    WritebackApplyRequest,
    WritebackApplyResult,
    get_writeback_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/writeback", tags=["wiki-writeback"])


class GenerateReviewSlipRequest(BaseModel):
    task_id: str
    task_title: str
    candidate_insights: list[dict[str, str]] = Field(default_factory=list)


class WikiLayersStats(BaseModel):
    agent_id: str
    raw_files_count: int
    sources_count: int
    concepts_count: int
    claims_count: int
    methods_count: int
    templates_count: int
    deliverables_count: int
    inbox_count: int


@router.post("/ledger", response_model=dict[str, str])
async def record_task_ledger(
    record: UsageLedgerRecord,
    agent_id: str = Query("default", description="Target agent ID"),
    workspace_root: Path = Depends(get_workspace_root),
) -> dict[str, str]:
    """Persist a task execution usage ledger."""
    service = get_writeback_service(workspace_root=workspace_root)
    path = service.record_usage_ledger(agent_id, record)
    return {"status": "ok", "saved_path": str(path)}


@router.post("/review-slips", response_model=ReviewSlipBatch)
async def generate_review_slips(
    payload: GenerateReviewSlipRequest,
    agent_id: str = Query("default", description="Target agent ID"),
    workspace_root: Path = Depends(get_workspace_root),
) -> ReviewSlipBatch:
    """Generate 1-5 decision review questions for task author with negative rule filtering."""
    service = get_writeback_service(workspace_root=workspace_root)
    return service.generate_review_slip(
        agent_id=agent_id,
        task_id=payload.task_id,
        task_title=payload.task_title,
        candidate_insights=payload.candidate_insights,
    )


@router.post("/apply", response_model=WritebackApplyResult)
async def apply_writeback_decisions(
    request: WritebackApplyRequest,
    agent_id: str = Query("default", description="Target agent ID"),
    workspace_root: Path = Depends(get_workspace_root),
) -> WritebackApplyResult:
    """Commit user decisions from review slips into corresponding knowledge layers."""
    service = get_writeback_service(workspace_root=workspace_root)
    return service.apply_writeback(agent_id, request)


@router.get("/layers-stats", response_model=WikiLayersStats)
async def get_wiki_layers_stats(
    agent_id: str = Query("default", description="Target agent ID"),
) -> WikiLayersStats:
    """Inspect file counts across all 5 production Wiki layers."""
    vault_path = resolve_wiki_vault_path(agent_id)
    structure = WikiStructure(base_dir=vault_path)
    structure.ensure_structure()

    def count_files(dir_path: Path) -> int:
        if not dir_path.is_dir():
            return 0
        return sum(1 for p in dir_path.rglob("*") if p.is_file() and not p.name.startswith("."))

    return WikiLayersStats(
        agent_id=agent_id,
        raw_files_count=count_files(structure.raw_dir),
        sources_count=count_files(structure.sources_dir),
        concepts_count=count_files(structure.concepts_dir),
        claims_count=count_files(structure.claims_dir),
        methods_count=count_files(structure.methods_dir),
        templates_count=count_files(structure.templates_dir),
        deliverables_count=count_files(structure.deliverables_dir),
        inbox_count=count_files(structure.inbox_dir),
    )


@router.get("/layer-items", response_model=list[WikiLayerItem])
async def get_wiki_layer_items(
    layer: str = Query(..., description="Target layer key, e.g. methods, claims, deliverables, sources, raw"),
    agent_id: str = Query("default", description="Target agent ID"),
    limit: int = Query(30, description="Max documents to return"),
    workspace_root: Path = Depends(get_workspace_root),
) -> list[WikiLayerItem]:
    """Retrieve list of documents inside a specific layer with metadata snippet."""
    service = get_writeback_service(workspace_root=workspace_root)
    return service.list_layer_items(agent_id=agent_id, layer_key=layer, limit=limit)

