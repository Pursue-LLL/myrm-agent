"""Integration Memory REST API endpoints.

[INPUT]
- app.services.memory.integration_memory (POS: Integration Memory business service)

[OUTPUT]
- router: FastAPI APIRouter with integration memory endpoints.

[POS]
REST API layer for Integration Memory. Exposes sync, browse, status, and
remove operations for the frontend to consume.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.memory.integration_memory import (
    IntegrationMemoryService,
    IntegrationStatusSnapshot,
    IntegrationTreeNodeDTO,
    get_integration_memory_service,
)

logger = logging.getLogger(__name__)

router = APIRouter()


class SyncRequest(BaseModel):
    provider_id: str = Field(default="", description="Specific provider to sync (empty = all)")
    account_key: str = Field(default="", description="Account within the provider")
    max_items: int = Field(default=200, ge=1, le=1000)


class SyncResultItem(BaseModel):
    provider: str
    account_key: str = ""
    created: int = 0
    updated: int = 0
    skipped: int = 0
    failed: int = 0
    elapsed_seconds: float = 0.0
    errors: list[str] = Field(default_factory=list)


class RemoveTreeResponse(BaseModel):
    tree_id: str
    deleted_elements: int


class ProvidersResponse(BaseModel):
    providers: list[str]


async def _get_service() -> IntegrationMemoryService:
    svc = await get_integration_memory_service()
    if svc is None:
        raise HTTPException(
            status_code=503,
            detail="Integration Memory service is not available. No providers are configured.",
        )
    return svc


@router.post("/sync", response_model=list[SyncResultItem])
async def sync_integration(req: SyncRequest) -> list[SyncResultItem]:
    """Trigger data sync from external service integrations."""
    svc = await _get_service()
    if req.provider_id:
        result = await svc.sync_provider(req.provider_id, account_key=req.account_key, max_items=req.max_items)
        results = [result]
    else:
        results = await svc.sync_all(max_items=req.max_items)

    return [
        SyncResultItem(
            provider=r.provider,
            account_key=r.account_key,
            created=r.created,
            updated=r.updated,
            skipped=r.skipped,
            failed=r.failed,
            elapsed_seconds=round(r.elapsed_seconds, 2),
            errors=r.errors,
        )
        for r in results
    ]


@router.get("/status", response_model=IntegrationStatusSnapshot)
async def integration_status() -> IntegrationStatusSnapshot:
    """Get integration memory status overview."""
    svc = await _get_service()
    return svc.get_status()


@router.get("/trees", response_model=list[IntegrationTreeNodeDTO])
async def list_trees(provider: str = "") -> list[IntegrationTreeNodeDTO]:
    """List all integration trees, optionally filtered by provider."""
    svc = await _get_service()
    trees = svc.list_trees(provider=provider)
    return [
        IntegrationTreeNodeDTO(
            id=t.id,
            labels=[t.provider],
            properties={
                "tree_id": t.id,
                "provider": t.provider,
                "account_key": t.account_key,
                "leaf_count": t.leaf_count,
                "root_summary": t.root_summary[:200] if t.root_summary else "",
            },
        )
        for t in trees
    ]


@router.get("/trees/{tree_id}", response_model=list[IntegrationTreeNodeDTO])
async def get_tree_structure(tree_id: str) -> list[IntegrationTreeNodeDTO]:
    """Get the full tree structure for a specific integration tree."""
    svc = await _get_service()
    nodes = await svc.get_tree_structure(tree_id)
    if not nodes:
        raise HTTPException(status_code=404, detail=f"Tree '{tree_id}' not found")
    return nodes


@router.delete("/trees/{tree_id}", response_model=RemoveTreeResponse)
async def remove_tree(tree_id: str) -> RemoveTreeResponse:
    """Remove an integration tree and all its indexed data."""
    svc = await _get_service()
    deleted = await svc.remove_tree(tree_id)
    return RemoveTreeResponse(tree_id=tree_id, deleted_elements=deleted)


@router.get("/providers", response_model=ProvidersResponse)
async def list_providers() -> ProvidersResponse:
    """List registered integration providers."""
    svc = await _get_service()
    return ProvidersResponse(providers=svc.provider_ids)
