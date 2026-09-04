"""Wiki Knowledge Governance API routes.

[INPUT]
- fastapi::APIRouter, Depends, HTTPException, Query
- pydantic::BaseModel, Field
- app.api.dependencies::get_optional_llm_for_user
- app.services.wiki::MemoryToWikiArchiver
- app.services.wiki.governance::WikiGovernanceFreshnessService

[OUTPUT]
- router: Governance API endpoints (/wiki/governance/overview, /wiki/governance/extend, /wiki/governance/archive, /wiki/governance/undo, /wiki/governance/revive)

[POS]
REST API boundary for KnowledgeGovernanceWorkbenchExpiryArchiveRevival.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.services.wiki import MemoryToWikiArchiver

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/governance", tags=["wiki-governance"])


class GovernanceExtendBody(BaseModel):
    concept_names: list[str] = Field(..., description="List of concept names to extend")


class GovernanceArchiveBody(BaseModel):
    concept_names: list[str] = Field(..., description="List of concept names to archive")
    reason: str = Field(default="", description="Optional archive reason")


class GovernanceUndoBody(BaseModel):
    undo_token: str = Field(..., description="Undo token returned from batch archive")


class GovernanceReviveBody(BaseModel):
    concept_names: list[str] = Field(..., description="List of archived concept names to revive")


def _get_archiver(agent_id: str | None = None) -> MemoryToWikiArchiver:
    return MemoryToWikiArchiver.get_instance(
        llm=None,
        agent_id=agent_id,
        enable_structural_cache=True,
    )


@router.get("/overview")
async def get_governance_overview(
    agent_id: Annotated[str | None, Query(description="Agent ID scope")] = None,
    threshold_days: Annotated[int, Query(description="Freshness threshold in days")] = 90,
) -> dict[str, object]:
    """Get the 4-queue governance workbench overview."""
    archiver = _get_archiver(agent_id)
    from app.services.wiki.governance import WikiGovernanceFreshnessService

    pending_count = archiver._pending_mgr.count_synthesis_pending() if hasattr(archiver, "_pending_mgr") else 0
    service = WikiGovernanceFreshnessService(
        structure=archiver._structure,
        indexer=archiver._indexer,
        freshness_threshold_days=threshold_days,
    )
    res = service.get_governance_overview(pending_count=pending_count)
    return res.to_dict()


@router.post("/extend")
async def extend_concepts_endpoint(
    body: GovernanceExtendBody,
    agent_id: Annotated[str | None, Query(description="Agent ID scope")] = None,
    threshold_days: Annotated[int, Query(description="Freshness threshold in days")] = 90,
) -> dict[str, object]:
    """Extend concept lifespan by resetting expiration clock."""
    archiver = _get_archiver(agent_id)
    from app.services.wiki.governance import WikiGovernanceFreshnessService

    service = WikiGovernanceFreshnessService(
        structure=archiver._structure,
        indexer=archiver._indexer,
        freshness_threshold_days=threshold_days,
    )
    result = service.extend_concepts(body.concept_names)
    return result.to_dict()


@router.post("/archive")
async def archive_concepts_endpoint(
    body: GovernanceArchiveBody,
    agent_id: Annotated[str | None, Query(description="Agent ID scope")] = None,
) -> dict[str, object]:
    """Atomically archive concepts into isolated directory and unindex from FTS5."""
    archiver = _get_archiver(agent_id)
    from app.services.wiki.governance import WikiGovernanceFreshnessService

    service = WikiGovernanceFreshnessService(
        structure=archiver._structure,
        indexer=archiver._indexer,
    )
    result = await service.archive_concepts(body.concept_names, reason=body.reason)
    return result.to_dict()


@router.post("/undo")
async def undo_archive_endpoint(
    body: GovernanceUndoBody,
    agent_id: Annotated[str | None, Query(description="Agent ID scope")] = None,
) -> dict[str, object]:
    """Undo a recent batch archive operation within 30 seconds."""
    archiver = _get_archiver(agent_id)
    from app.services.wiki.governance import WikiGovernanceFreshnessService

    service = WikiGovernanceFreshnessService(
        structure=archiver._structure,
        indexer=archiver._indexer,
    )
    result = await service.undo_archive(body.undo_token)
    return result.to_dict()


@router.post("/revive")
async def revive_concepts_endpoint(
    body: GovernanceReviveBody,
    agent_id: Annotated[str | None, Query(description="Agent ID scope")] = None,
) -> dict[str, object]:
    """Revive archived concepts back into active concepts directory and reindex."""
    archiver = _get_archiver(agent_id)
    from app.services.wiki.governance import WikiGovernanceFreshnessService

    service = WikiGovernanceFreshnessService(
        structure=archiver._structure,
        indexer=archiver._indexer,
    )
    result = await service.revive_concepts(body.concept_names)
    return result.to_dict()
