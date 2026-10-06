"""
[POS] app/services/memory/memory_crystallization_service.py
[INPUT] app.schemas.memory_crystallization, myrm_agent_harness.toolkits.memory.crystallization
[OUTPUT] MemoryCrystallizationService, get_memory_crystallization_service

Singleton service coordinating procedural memory crystallization lifecycle, formation gating, and self-correction.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from myrm_agent_harness.toolkits.memory.crystallization import (
    CrystallizedRuleMetrics,
    ProceduralCrystallizationGovernor,
    RuleLifecycleState,
)

from app.schemas.memory_crystallization import (
    CrystallizedRuleMetricsDTO,
    EvaluateFormationRequestDTO,
    EvaluateFormationResponseDTO,
    FilterFacetsRequestDTO,
    FilterFacetsResponseDTO,
    RecordFeedbackRequestDTO,
    RecordFeedbackResponseDTO,
)


def _to_rule_metrics_dto(metrics: CrystallizedRuleMetrics) -> CrystallizedRuleMetricsDTO:
    """Convert harness CrystallizedRuleMetrics to API DTO."""
    return CrystallizedRuleMetricsDTO(
        rule_id=metrics.rule_id,
        facets=list(metrics.facets),
        success_count=metrics.success_count,
        fail_count=metrics.fail_count,
        win_rate=metrics.win_rate,
        state=metrics.state.value,
        weight=metrics.weight,
        description=metrics.description,
    )


def _from_rule_metrics_dto(dto: CrystallizedRuleMetricsDTO) -> CrystallizedRuleMetrics:
    """Convert API DTO to harness CrystallizedRuleMetrics."""
    return CrystallizedRuleMetrics(
        rule_id=dto.rule_id,
        facets=list(dto.facets),
        success_count=dto.success_count,
        fail_count=dto.fail_count,
        win_rate=dto.win_rate,
        state=RuleLifecycleState(dto.state),
        weight=dto.weight,
        description=dto.description,
    )


class MemoryCrystallizationService:
    """Service providing formation gating, facet routing, and reflection feedback loops."""

    def __init__(self, governor: ProceduralCrystallizationGovernor | None = None) -> None:
        self._governor = governor or ProceduralCrystallizationGovernor()

    def evaluate_formation_gate(
        self,
        request: EvaluateFormationRequestDTO,
    ) -> EvaluateFormationResponseDTO:
        """Evaluate two-factor importance gate (confidence x severity >= 0.70)."""
        result = self._governor.evaluate_formation_gate(
            confidence=request.confidence,
            severity=request.severity,
            content=request.content,
        )
        return EvaluateFormationResponseDTO(
            confidence=result.confidence,
            severity=result.severity,
            importance=result.importance,
            passed_gate=result.passed_gate,
            gate_reason=result.gate_reason,
        )

    def filter_by_facets(
        self,
        request: FilterFacetsRequestDTO,
    ) -> FilterFacetsResponseDTO:
        """Filter candidate rule list by active operational domain facets."""
        harness_rules = [_from_rule_metrics_dto(r) for r in request.rules]
        matched = self._governor.filter_by_facets(
            rules=harness_rules,
            active_facets=request.active_facets,
        )
        matched_dtos = [_to_rule_metrics_dto(m) for m in matched]
        return FilterFacetsResponseDTO(
            active_facets=request.active_facets,
            matched_rules=matched_dtos,
            total_candidates=len(request.rules),
            matched_count=len(matched_dtos),
        )

    def record_execution_feedback(
        self,
        request: RecordFeedbackRequestDTO,
    ) -> RecordFeedbackResponseDTO:
        """Record rule execution feedback, apply same-session repeat error penalty, and evolve lifecycle state."""
        prev_fail = 0
        existing = self._governor.get_metrics(request.rule_id)
        if existing is not None:
            prev_fail = existing.fail_count

        updated = self._governor.record_execution_feedback(
            rule_id=request.rule_id,
            session_id=request.session_id,
            is_success=request.is_success,
            secondary_error_occurred=request.secondary_error_occurred,
            description=request.description,
            facets=request.facets,
        )

        # Detect whether repeat penalty (+2) occurred
        repeat_penalized = bool(not request.is_success and (updated.fail_count - prev_fail >= 2))

        return RecordFeedbackResponseDTO(
            metrics=_to_rule_metrics_dto(updated),
            repeat_failure_penalized=repeat_penalized,
        )

    def get_rule_metrics(self, rule_id: str) -> CrystallizedRuleMetricsDTO | None:
        """Retrieve current metrics and lifecycle state for a given rule."""
        metrics = self._governor.get_metrics(rule_id)
        return _to_rule_metrics_dto(metrics) if metrics is not None else None


_service_instance: MemoryCrystallizationService | None = None


def get_memory_crystallization_service() -> MemoryCrystallizationService:
    """Retrieve singleton instance of MemoryCrystallizationService."""
    global _service_instance
    if _service_instance is None:
        _service_instance = MemoryCrystallizationService()
    return _service_instance
