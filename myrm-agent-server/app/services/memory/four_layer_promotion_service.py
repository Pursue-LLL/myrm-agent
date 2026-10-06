"""Business service managing Four-Layer Memory Tri-Channel Promotion and Anti-Poisoning Audit.

[INPUT]
- myrm_agent_harness.toolkits.memory.strategies.four_layer_promotion::TwoStepMapReduceConsolidationEngine
- myrm_agent_harness.toolkits.memory.strategies.four_layer_promotion::AntiPoisoningAuditTracker
- myrm_agent_harness.toolkits.memory.strategies.four_layer_promotion::CandidateStatement, ExposureSource, CapabilityMethod
- app.schemas.four_layer_promotion::ConsolidationMapRequest, ConsolidationMapResponse
- app.schemas.four_layer_promotion::ConsolidationReduceRequest, ConsolidationReduceResponse
- app.schemas.four_layer_promotion::RulesComplianceRequest, RulesComplianceResponse
- app.schemas.four_layer_promotion::BatchRollbackResponse, CapabilityMethodSchema, PromotionDecisionSchema

[OUTPUT]
- FourLayerPromotionService: singleton/scoped service coordinating Map-Reduce pipeline,
  tri-channel code assertions, and atomic rollback.

[POS]
Server-side business service executing Hermes-grade two-step consolidation
and anti-poisoning lineage audit.
"""

from __future__ import annotations

import logging
from typing import Final

from myrm_agent_harness.toolkits.memory.strategies.four_layer_promotion import (
    AntiPoisoningAuditTracker,
    CandidateStatement,
    ExposureSource,
    TwoStepMapReduceConsolidationEngine,
)

from app.schemas.four_layer_promotion import (
    BatchRollbackResponse,
    CandidateStatementSchema,
    CapabilityMethodSchema,
    ConsolidationMapRequest,
    ConsolidationMapResponse,
    ConsolidationReduceRequest,
    ConsolidationReduceResponse,
    PromotionDecisionSchema,
    RulesComplianceItemSchema,
    RulesComplianceRequest,
    RulesComplianceResponse,
)

logger: Final[logging.Logger] = logging.getLogger(__name__)


class FourLayerPromotionService:
    """Service governing Map-Reduce memory consolidation and anti-poisoning audit lineage."""

    def __init__(
        self,
        engine: TwoStepMapReduceConsolidationEngine | None = None,
        tracker: AntiPoisoningAuditTracker | None = None,
    ) -> None:
        self._engine: Final[TwoStepMapReduceConsolidationEngine] = engine or TwoStepMapReduceConsolidationEngine()
        self._tracker: Final[AntiPoisoningAuditTracker] = tracker or AntiPoisoningAuditTracker()

    def map_session(self, request: ConsolidationMapRequest) -> ConsolidationMapResponse:
        """Map phase: extract self-contained candidate statements from raw session events."""
        raw_events: list[dict[str, str | bool]] = [
            {
                "id": evt.id,
                "content": evt.content,
                "failed": evt.failed,
                "explicit_instruction": evt.explicit_instruction,
            }
            for evt in request.events
        ]
        exposure = (
            ExposureSource.EXTERNAL_UNTRUSTED
            if request.exposure_source == "external_untrusted"
            else ExposureSource.INTERNAL_CHAT
        )

        candidates = self._engine.map_session(
            session_id=request.session_id,
            events=raw_events,
            exposure_source=exposure,
        )

        schema_candidates = [
            CandidateStatementSchema(
                statement=c.statement,
                supported_event_ids=list(c.supported_event_ids),
                session_id=c.session_id,
                exposure_source=c.exposure_source.value,
                has_tool_failure=c.has_tool_failure,
                is_explicit_user_instruction=c.is_explicit_user_instruction,
            )
            for c in candidates
        ]
        return ConsolidationMapResponse(
            session_id=request.session_id,
            candidates=schema_candidates,
        )

    def reduce_candidates(self, request: ConsolidationReduceRequest) -> ConsolidationReduceResponse:
        """Reduce phase: evaluate tri-channel promotion gates and register batch audit lineage."""
        candidates = [
            CandidateStatement(
                statement=cs.statement,
                supported_event_ids=tuple(cs.supported_event_ids),
                session_id=cs.session_id,
                exposure_source=(
                    ExposureSource.EXTERNAL_UNTRUSTED
                    if cs.exposure_source == "external_untrusted"
                    else ExposureSource.INTERNAL_CHAT
                ),
                has_tool_failure=cs.has_tool_failure,
                is_explicit_user_instruction=cs.is_explicit_user_instruction,
            )
            for cs in request.candidates
        ]

        methods, decisions = self._engine.reduce_cross_session(candidates)
        batch_id = self._tracker.record_batch(methods)

        method_schemas = [
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
            for m in methods
        ]

        decision_schemas = [
            PromotionDecisionSchema(
                promoted=d.promoted,
                channel=d.channel.value if d.channel else None,
                reason=d.reason,
                method_id=d.method_card.method_id if d.method_card else None,
            )
            for d in decisions
        ]

        return ConsolidationReduceResponse(
            batch_id=batch_id,
            promoted_methods=method_schemas,
            decisions=decision_schemas,
        )

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
