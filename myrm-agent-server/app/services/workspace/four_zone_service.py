"""Server service for Four-Zone Workspace Layout and Read-Only Source Protection.

[INPUT]
- DTO requests from app.schemas.four_zone
- Harness primitives: FourZoneScaffold, FourZoneProtectionGuard, OneWayPromotionPipeline

[OUTPUT]
- FourZoneService: Workspace layout manager, permission evaluator, and promotion coordinator
- get_four_zone_service: Singleton provider

[POS]
Server workspace service. Manages customer sandbox folders across the four zones,
protecting client original documents and orchestrating verified artifact promotions.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.core.security.four_zone import (
    FourZoneProtectionGuard,
    FourZoneScaffold,
    OneWayPromotionPipeline,
    ReadOnlySourceZoneViolationError,
    WorkspaceZone,
    ZoneOperationType,
    ZonePromotionRecord,
    ZoneValidationResult,
)

from app.schemas.four_zone import (
    FourZoneCheckRequest,
    FourZoneCheckResponse,
    FourZoneInitRequest,
    FourZoneInitResponse,
    FourZonePromotionRequest,
    FourZonePromotionResponse,
    FourZoneReplicateRequest,
    FourZoneReplicateResponse,
)

logger = logging.getLogger(__name__)


class FourZoneService:
    """Manages workspace four-zone topology, permission checking, and artifact promotions."""

    @classmethod
    def initialize_workspace(cls, request: FourZoneInitRequest) -> FourZoneInitResponse:
        """Create standard 4-zone layout under the specified workspace root."""
        created = FourZoneScaffold.initialize_workspace(request.workspace_root)
        return FourZoneInitResponse(
            zones=created,
            status="success",
            message=f"Four-zone layout successfully initialized at '{request.workspace_root}'",
        )

    @classmethod
    def check_operation(cls, request: FourZoneCheckRequest) -> FourZoneCheckResponse:
        """Evaluate whether a file operation is permitted according to zone protection rules."""
        try:
            op_enum = ZoneOperationType(request.operation)
            val_result: ZoneValidationResult = FourZoneProtectionGuard.assert_operation_allowed(
                file_path=request.file_path,
                operation=op_enum,
            )
            return FourZoneCheckResponse(
                allowed=val_result.allowed,
                zone=val_result.zone.value if val_result.zone else None,
                reason=val_result.reason,
            )
        except ReadOnlySourceZoneViolationError as exc:
            return FourZoneCheckResponse(
                allowed=False,
                zone=WorkspaceZone.ZONE_01_RAW.value,
                reason=str(exc),
            )

    @classmethod
    def replicate_to_draft(cls, request: FourZoneReplicateRequest) -> FourZoneReplicateResponse:
        """Safely copy raw document from Zone 01 into Zone 02 draft for editing."""
        draft_full_path = FourZoneProtectionGuard.replicate_to_draft(
            root_dir=request.workspace_root,
            source_rel_path=request.source_rel_path,
            draft_rel_path=request.draft_rel_path,
        )
        return FourZoneReplicateResponse(
            draft_full_path=draft_full_path,
            message="Successfully replicated Zone 01 original into Zone 02 draft",
        )

    @classmethod
    def promote(cls, request: FourZonePromotionRequest) -> FourZonePromotionResponse:
        """Execute validated forward promotion of an artifact across zones."""
        record: ZonePromotionRecord
        if request.promotion_type == "draft_to_canonical":
            record = OneWayPromotionPipeline.promote_draft_to_canonical(
                root_dir=request.workspace_root,
                draft_rel_path=request.source_rel_path,
                canonical_rel_path=request.target_rel_path,
                reviewer_id=request.reviewer_id,
            )
        else:
            record = OneWayPromotionPipeline.promote_canonical_to_deliverable(
                root_dir=request.workspace_root,
                canonical_rel_path=request.source_rel_path,
                deliverable_rel_path=request.target_rel_path,
                reviewer_id=request.reviewer_id,
            )

        return FourZonePromotionResponse(
            promotion_id=record.promotion_id,
            source_zone=record.source_zone.value,
            target_zone=record.target_zone.value,
            source_path=record.source_path,
            target_path=record.target_path,
            promoted_by=record.promoted_by,
            promoted_at=record.promoted_at,
        )


_global_four_zone_service: FourZoneService | None = None


def get_four_zone_service() -> FourZoneService:
    """Singleton getter for FourZoneService."""
    global _global_four_zone_service
    if _global_four_zone_service is None:
        _global_four_zone_service = FourZoneService()
    return _global_four_zone_service
