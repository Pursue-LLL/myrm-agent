"""Business service managing Four-Layer Memory Tri-Channel Promotion and Anti-Poisoning Audit.

[INPUT]
- myrm_agent_harness.toolkits.memory.strategies.four_layer_promotion::TwoStepMapReduceConsolidationEngine
- myrm_agent_harness.toolkits.memory.strategies.four_layer_promotion::AntiPoisoningAuditTracker
- app.schemas.four_layer_promotion::RulesComplianceRequest, RulesComplianceResponse
- app.schemas.four_layer_promotion::BatchRollbackResponse, CapabilityMethodSchema

[OUTPUT]
- FourLayerPromotionService: singleton/scoped service coordinating rules-compliance checks
  and atomic rollback.

[POS]
Server-side business service verifying rules compliance and rolling back promoted
capability methods through the anti-poisoning audit lineage.
"""

from __future__ import annotations

import logging
from typing import Final

from myrm_agent_harness.toolkits.memory.strategies.four_layer_promotion import (
    AntiPoisoningAuditTracker,
    TwoStepMapReduceConsolidationEngine,
)

from app.schemas.four_layer_promotion import (
    BatchRollbackResponse,
    CapabilityMethodSchema,
    RulesComplianceItemSchema,
    RulesComplianceRequest,
    RulesComplianceResponse,
)

logger: Final[logging.Logger] = logging.getLogger(__name__)


class FourLayerPromotionService:
    """Service verifying rules compliance and rolling back promoted capability methods."""

    def __init__(
        self,
        engine: TwoStepMapReduceConsolidationEngine | None = None,
        tracker: AntiPoisoningAuditTracker | None = None,
    ) -> None:
        self._engine: Final[TwoStepMapReduceConsolidationEngine] = engine or TwoStepMapReduceConsolidationEngine()
        self._tracker: Final[AntiPoisoningAuditTracker] = tracker or AntiPoisoningAuditTracker()

    def verify_compliance(self, request: RulesComplianceRequest) -> RulesComplianceResponse:
        """Evaluate response text against all currently active capability method rules."""
        active_methods = self._tracker.get_active_methods()
        items = self._engine.evaluate_rules_compliance(
            response_text=request.response_text,
            active_methods=active_methods,
        )

        item_schemas = [
            RulesComplianceItemSchema(
                rule_id=it.rule_id,
                statement=it.statement,
                compliant=it.compliant,
                rationale=it.rationale,
            )
            for it in items
        ]
        all_ok = all(it.compliant for it in items) if items else True
        return RulesComplianceResponse(
            items=item_schemas,
            all_compliant=all_ok,
        )

    def rollback_batch(self, batch_id: str) -> BatchRollbackResponse:
        """Atomically rollback all capability methods promoted during the specified batch."""
        success, reverted_ids = self._tracker.rollback_batch(batch_id)
        return BatchRollbackResponse(
            batch_id=batch_id,
            success=success,
            reverted_method_ids=reverted_ids,
        )

    def get_active_methods(self) -> list[CapabilityMethodSchema]:
        """Return list of all currently active capability method schemas."""
        return [
            CapabilityMethodSchema(
                method_id=m.method_id,
                title=m.title,
                applies_when=m.applies_when,
                method_steps=list(m.method_steps),
                validation_criteria=m.validation_criteria,
                failure_signals=list(m.failure_signals),
                supported_event_ids=list(m.supported_event_ids),
                promotion_channel=m.promotion_channel.value,
            )
            for m in self._tracker.get_active_methods()
        ]


_DEFAULT_SERVICE: FourLayerPromotionService | None = None


def get_four_layer_promotion_service() -> FourLayerPromotionService:
    """Return the singleton instance of FourLayerPromotionService."""
    global _DEFAULT_SERVICE
    if _DEFAULT_SERVICE is None:
        _DEFAULT_SERVICE = FourLayerPromotionService()
    return _DEFAULT_SERVICE
