"""[POS]: app/api/memory/progressive_sidecar_router.py
[INPUT]: HTTP requests for generating L0/L1/L2 sidecars and tiered context reads.
[OUTPUT]: FastAPI APIRouter endpoints delivering three-tier progressive context disclosure.
"""

from fastapi import APIRouter, Depends, HTTPException
from myrm_agent_harness.toolkits.memory import (
    ContextTier,
    CVFSProtocolError,
)

from app.schemas.progressive_sidecar import (
    ContextTierAPIEnum,
    GenerateSidecarsRequest,
    OKFFrontmatterResponse,
    ProgressiveBundleResponse,
    ReadTieredRequest,
    ReadTieredResponse,
    WriteWithSidecarsRequest,
)
from app.services.memory.progressive_sidecar_service import (
    ProgressiveSidecarService,
    get_progressive_sidecar_service,
)

router = APIRouter(prefix="/progressive-sidecar", tags=["memory_progressive_sidecar"])


def _map_tier_enum(api_tier: ContextTierAPIEnum) -> ContextTier:
    """Map API tier enum to harness domain ContextTier."""
    if api_tier == ContextTierAPIEnum.L0_ABSTRACT:
        return ContextTier.L0_ABSTRACT
    if api_tier == ContextTierAPIEnum.L1_OVERVIEW:
        return ContextTier.L1_OVERVIEW
    return ContextTier.L2_DETAIL


@router.post("/generate-bundle", response_model=ProgressiveBundleResponse)
def generate_progressive_bundle(
    req: GenerateSidecarsRequest,
    service: ProgressiveSidecarService = Depends(get_progressive_sidecar_service),
) -> ProgressiveBundleResponse:
    """Synthesize L0 abstract, L1 overview, and OKF frontmatter bundle in memory."""
    try:
        bundle = service.generate_bundle(uri=req.uri, content=req.content, title=req.title)
    except CVFSProtocolError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return ProgressiveBundleResponse(
        doc_id=bundle.doc_id,
        frontmatter=OKFFrontmatterResponse(
            doc_id=bundle.frontmatter.doc_id,
            title=bundle.frontmatter.title,
            digest_sha256=bundle.frontmatter.digest_sha256,
            l0_tokens_est=bundle.frontmatter.l0_tokens_est,
            l1_tokens_est=bundle.frontmatter.l1_tokens_est,
            l2_tokens_est=bundle.frontmatter.l2_tokens_est,
            updated_at_epoch=bundle.frontmatter.updated_at_epoch,
        ),
        l0_abstract=bundle.l0_abstract,
        l1_overview=bundle.l1_overview,
        l2_detail=bundle.l2_detail,
        token_savings_pct=bundle.token_savings_pct,
    )


@router.post("/write-with-sidecars", response_model=ProgressiveBundleResponse)
def write_with_sidecars(
    req: WriteWithSidecarsRequest,
    service: ProgressiveSidecarService = Depends(get_progressive_sidecar_service),
) -> ProgressiveBundleResponse:
    """Persist primary L2 document and automatically generate and persist companion L0/L1 sidecars into VFS."""
    try:
        bundle = service.write_with_sidecars(
            uri=req.uri,
            content=req.content,
            title=req.title,
            metadata=req.metadata,
        )
    except CVFSProtocolError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return ProgressiveBundleResponse(
        doc_id=bundle.doc_id,
        frontmatter=OKFFrontmatterResponse(
            doc_id=bundle.frontmatter.doc_id,
            title=bundle.frontmatter.title,
            digest_sha256=bundle.frontmatter.digest_sha256,
            l0_tokens_est=bundle.frontmatter.l0_tokens_est,
            l1_tokens_est=bundle.frontmatter.l1_tokens_est,
            l2_tokens_est=bundle.frontmatter.l2_tokens_est,
            updated_at_epoch=bundle.frontmatter.updated_at_epoch,
        ),
        l0_abstract=bundle.l0_abstract,
        l1_overview=bundle.l1_overview,
        l2_detail=bundle.l2_detail,
        token_savings_pct=bundle.token_savings_pct,
    )


@router.post("/read-tiered", response_model=ReadTieredResponse)
def read_tiered_context(
    req: ReadTieredRequest,
    service: ProgressiveSidecarService = Depends(get_progressive_sidecar_service),
) -> ReadTieredResponse:
    """Read document at specified granularity tier (L0/L1/L2) with automatic fallback synthesis."""
    harness_tier = _map_tier_enum(req.tier)
    try:
        res = service.read_tiered(uri=req.uri, tier=harness_tier)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except CVFSProtocolError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return ReadTieredResponse(
        uri=res.uri,
        tier=res.tier.value,
        content=res.content,
        token_est=res.token_est,
        has_higher_detail=res.has_higher_detail,
    )
