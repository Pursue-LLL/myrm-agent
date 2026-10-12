"""API router for On-Demand Credential Materialization and Multi-Encoding Secret Masking."""

from fastapi import APIRouter, Depends

from app.schemas.on_demand_masking import (
    MaskTextRequest,
    MaskTextResponse,
    ResolveAndExecuteRequest,
    ResolveAndExecuteResponse,
)
from app.services.security.on_demand_masking_service import (
    OnDemandMaskingService,
    get_on_demand_masking_service,
)

router = APIRouter(prefix="/on-demand-masking", tags=["security", "on-demand-masking"])


@router.post("/mask-text", response_model=MaskTextResponse)
async def mask_text(
    request: MaskTextRequest,
    service: OnDemandMaskingService = Depends(get_on_demand_masking_service),
) -> MaskTextResponse:
    """Mask secret variables in text across raw, URL, and Base64 representations."""
    return service.mask_text(request)


@router.post("/resolve-and-execute", response_model=ResolveAndExecuteResponse)
async def resolve_and_execute(
    request: ResolveAndExecuteRequest,
    service: OnDemandMaskingService = Depends(get_on_demand_masking_service),
) -> ResolveAndExecuteResponse:
    """Resolve requested credentials on demand and execute command with masked output."""
    return service.resolve_and_execute(request)
