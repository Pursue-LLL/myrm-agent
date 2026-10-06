"""API router for Four-Layer Memory Tri-Channel Promotion and Anti-Poisoning Audit.

[INPUT]
- fastapi::APIRouter, Depends
- app.schemas.four_layer_promotion::ConsolidationMapRequest, ConsolidationMapResponse
- app.schemas.four_layer_promotion::ConsolidationReduceRequest, ConsolidationReduceResponse
- app.schemas.four_layer_promotion::RulesComplianceRequest, RulesComplianceResponse
- app.schemas.four_layer_promotion::BatchRollbackRequest, BatchRollbackResponse, CapabilityMethodSchema
- app.services.memory.four_layer_promotion_service::FourLayerPromotionService, get_four_layer_promotion_service

[OUTPUT]
- router: APIRouter exporting endpoints for Map extraction, Reduce promotion, compliance, and rollback

[POS]
REST API surface for Hermes-grade two-step memory consolidation, tri-channel code assertions,
and anti-poisoning lineage audit.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.schemas.four_layer_promotion import (
    BatchRollbackRequest,
    BatchRollbackResponse,
    CapabilityMethodSchema,
    ConsolidationMapRequest,
    ConsolidationMapResponse,
    ConsolidationReduceRequest,
    ConsolidationReduceResponse,
    RulesComplianceRequest,
    RulesComplianceResponse,
)
from app.services.memory.four_layer_promotion_service import (
    FourLayerPromotionService,
    get_four_layer_promotion_service,
)

router = APIRouter(prefix="/four-layer-promotion", tags=["memory-four-layer-promotion"])


@router.post("/map", response_model=ConsolidationMapResponse)
async def map_session_events(
    request: ConsolidationMapRequest,
    service: Annotated[FourLayerPromotionService, Depends(get_four_layer_promotion_service)],
) -> ConsolidationMapResponse:
    """Map phase: extract self-contained candidate statements from raw session events."""
    return service.map_session(request)


@router.post("/reduce", response_model=ConsolidationReduceResponse)
async def reduce_candidates(
    request: ConsolidationReduceRequest,
    service: Annotated[FourLayerPromotionService, Depends(get_four_layer_promotion_service)],
) -> ConsolidationReduceResponse:
    """Reduce phase: group synonymous statements, evaluate tri-channel gates, and promote methods."""
    return service.reduce_candidates(request)


@router.post("/verify-compliance", response_model=RulesComplianceResponse)
async def verify_rules_compliance(
    request: RulesComplianceRequest,
    service: Annotated[FourLayerPromotionService, Depends(get_four_layer_promotion_service)],
) -> RulesComplianceResponse:
    """Structured contract verification: evaluate output text compliance against active rules."""
    return service.verify_compliance(request)


@router.post("/rollback", response_model=BatchRollbackResponse)
async def rollback_consolidation_batch(
    request: BatchRollbackRequest,
    service: Annotated[FourLayerPromotionService, Depends(get_four_layer_promotion_service)],
) -> BatchRollbackResponse:
    """Atomic rollback: revoke all capability methods promoted during the specified batch."""
    return service.rollback_batch(request.batch_id)


@router.get("/active-methods", response_model=list[CapabilityMethodSchema])
async def list_active_capability_methods(
    service: Annotated[FourLayerPromotionService, Depends(get_four_layer_promotion_service)],
) -> list[CapabilityMethodSchema]:
    """Retrieve all currently active promoted capability method cards."""
    return service.get_active_methods()
