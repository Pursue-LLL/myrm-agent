"""Wiki Knowledge Governance API routes.

[INPUT]
- fastapi::APIRouter, Depends, Query
- pydantic::BaseModel, Field
- app.api.wiki.archiver_dependency::get_scoped_wiki_archiver
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

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.api.wiki.archiver_dependency import get_scoped_wiki_archiver
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


@router.get("/overview")
async def get_governance_overview(
    archiver: Annotated[MemoryToWikiArchiver, Depends(get_scoped_wiki_archiver)],
    threshold_days: Annotated[int, Query(description="Freshness threshold in days")] = 90,
) -> dict[str, object]:
    """Get the 4-queue governance workbench overview."""
    from app.services.wiki.governance import WikiGovernanceFreshnessService

    pending_count = archiver._pending_mgr.count_synthesis_pending()
    from myrm_agent_harness.toolkits.wiki.diagnostics.structural_lint import (
        collect_provenance_gap_issues,
    )

    try:
        gaps_count = len(collect_provenance_gap_issues(archiver._structure))
    except Exception:
        gaps_count = 0

    service = WikiGovernanceFreshnessService(
        structure=archiver._structure,
        indexer=archiver._query_engine._indexer,
        freshness_threshold_days=threshold_days,
    )
    res = service.get_governance_overview(pending_count=pending_count, gaps_count=gaps_count)
    return res.to_dict()


@router.post("/extend")
async def extend_concepts_endpoint(
    body: GovernanceExtendBody,
    archiver: Annotated[MemoryToWikiArchiver, Depends(get_scoped_wiki_archiver)],
    threshold_days: Annotated[int, Query(description="Freshness threshold in days")] = 90,
) -> dict[str, object]:
    """Extend concept lifespan by resetting expiration clock."""
    from app.services.wiki.governance import WikiGovernanceFreshnessService

    service = WikiGovernanceFreshnessService(
        structure=archiver._structure,
        indexer=archiver._query_engine._indexer,
        freshness_threshold_days=threshold_days,
    )
    result = service.extend_concepts(body.concept_names)
    return result.to_dict()


@router.post("/archive")
async def archive_concepts_endpoint(
    body: GovernanceArchiveBody,
    archiver: Annotated[MemoryToWikiArchiver, Depends(get_scoped_wiki_archiver)],
) -> dict[str, object]:
    """Atomically archive concepts into isolated directory and unindex from FTS5."""
    from app.services.wiki.governance import WikiGovernanceFreshnessService

    service = WikiGovernanceFreshnessService(
        structure=archiver._structure,
        indexer=archiver._query_engine._indexer,
    )
    result = await service.archive_concepts(body.concept_names, reason=body.reason)
    return result.to_dict()


@router.post("/undo")
async def undo_archive_endpoint(
    body: GovernanceUndoBody,
    archiver: Annotated[MemoryToWikiArchiver, Depends(get_scoped_wiki_archiver)],
) -> dict[str, object]:
    """Undo a recent batch archive operation within 30 seconds."""
    from app.services.wiki.governance import WikiGovernanceFreshnessService

    service = WikiGovernanceFreshnessService(
        structure=archiver._structure,
        indexer=archiver._query_engine._indexer,
    )
    result = await service.undo_archive(body.undo_token)
    return result.to_dict()


@router.post("/revive")
async def revive_concepts_endpoint(
    body: GovernanceReviveBody,
    archiver: Annotated[MemoryToWikiArchiver, Depends(get_scoped_wiki_archiver)],
) -> dict[str, object]:
    """Revive archived concepts back into active concepts directory and reindex."""
    from app.services.wiki.governance import WikiGovernanceFreshnessService

    service = WikiGovernanceFreshnessService(
        structure=archiver._structure,
        indexer=archiver._query_engine._indexer,
    )
    result = await service.revive_concepts(body.concept_names)
    return result.to_dict()


class HealClaimEvidenceBody(BaseModel):
    concept_names: list[str] = Field(..., description="List of concept names to heal claims for")


@router.post("/claims/heal")
async def heal_concept_claims_endpoint(
    body: HealClaimEvidenceBody,
    archiver: Annotated[MemoryToWikiArchiver, Depends(get_scoped_wiki_archiver)],
) -> dict[str, object]:
    """Auto-heal shifted line ranges and refresh content_sha256 for concept claims."""
    from myrm_agent_harness.toolkits.wiki.core.claims_contract import (
        heal_claim_evidence_snapshot,
    )

    total_healed = 0
    results: dict[str, int] = {}
    for name in body.concept_names:
        healed, count = heal_claim_evidence_snapshot(name, archiver._structure)
        if healed:
            total_healed += count
            results[name] = count

    return {
        "success": True,
        "total_healed_evidence": total_healed,
        "details": results,
    }
