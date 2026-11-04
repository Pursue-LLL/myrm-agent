"""Wiki 5-Layer structure REST routes.

[INPUT]
- fastapi::APIRouter, Depends, Query
- app.services.wiki.layers
- app.services.wiki.vault::resolve_wiki_vault_path
- myrm_agent_harness.toolkits.wiki.core.structure::WikiStructure

[OUTPUT]
- router (Layers sub-router)

[POS]
REST API endpoints for 5-layer structure file counts and per-layer document listing.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Query
from myrm_agent_harness.toolkits.wiki.core.structure import WikiStructure
from pydantic import BaseModel

from app.api.dependencies import get_workspace_root
from app.services.wiki.layers import WikiLayerItem, get_layers_service
from app.services.wiki.vault import resolve_wiki_vault_path

router = APIRouter(prefix="/layers", tags=["wiki-layers"])


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


@router.get("/stats", response_model=WikiLayersStats)
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


@router.get("/items", response_model=list[WikiLayerItem])
async def get_wiki_layer_items(
    layer: str = Query(..., description="Target layer key, e.g. methods, claims, deliverables, sources, raw"),
    agent_id: str = Query("default", description="Target agent ID"),
    limit: int = Query(30, description="Max documents to return"),
    workspace_root: Path = Depends(get_workspace_root),
) -> list[WikiLayerItem]:
    """Retrieve list of documents inside a specific layer with metadata snippet."""
    service = get_layers_service(workspace_root=workspace_root)
    return service.list_layer_items(agent_id=agent_id, layer_key=layer, limit=limit)
