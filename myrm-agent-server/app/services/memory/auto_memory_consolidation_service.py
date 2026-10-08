"""Domain service for Idle & Budget Gated Auto-Memory Consolidation Suite (Item 123).

[POS]
app/services/memory/auto_memory_consolidation_service.py

[INPUT]
- myrm_agent_harness.toolkits.memory.auto_consolidation, app.schemas.auto_memory_consolidation

[OUTPUT]
- AutoMemoryConsolidationService, get_auto_memory_consolidation_service
"""


from __future__ import annotations

import logging

from myrm_agent_harness.toolkits.memory import (
    AutoMemoryConsolidationOrchestrator,
    AutoMemoryGatingConfig,
    OverallGatingReport,
    SixDimensionalMemoryArtifact,
)

from app.schemas.auto_memory_consolidation import (
    AutoMemoryGatingConfigDTO,
    BudgetGatingDecisionDTO,
    ConsolidateSessionRequest,
    ConsolidateSessionResponse,
    EvaluateGatingRequest,
    EvaluateGatingResponse,
    IdleDetectionStateDTO,
    OverallGatingReportDTO,
    SixDimensionalMemoryArtifactDTO,
    TurnGatingDecisionDTO,
)

logger = logging.getLogger(__name__)


class AutoMemoryConsolidationService:
    """Domain service managing background session distillation with dual gating."""

    def __init__(self, orchestrator: AutoMemoryConsolidationOrchestrator | None = None) -> None:
        self._orchestrator = orchestrator or AutoMemoryConsolidationOrchestrator()

    def get_config(self) -> AutoMemoryGatingConfigDTO:
        """Retrieve active gating threshold configuration."""
        cfg = self._orchestrator.config
        return AutoMemoryGatingConfigDTO(
            enabled=cfg.enabled,
            idle_timeout_seconds=cfg.idle_timeout_seconds,
            min_turn_count=cfg.min_turn_count,
            min_info_density=cfg.min_info_density,
            min_remaining_budget_tokens=cfg.min_remaining_budget_tokens,
            max_consolidation_cost_ratio=cfg.max_consolidation_cost_ratio,
        )

    def update_config(self, dto: AutoMemoryGatingConfigDTO) -> AutoMemoryGatingConfigDTO:
        """Update active gating configuration."""
        new_config = AutoMemoryGatingConfig(
            enabled=dto.enabled,
            idle_timeout_seconds=dto.idle_timeout_seconds,
            min_turn_count=dto.min_turn_count,
            min_info_density=dto.min_info_density,
            min_remaining_budget_tokens=dto.min_remaining_budget_tokens,
            max_consolidation_cost_ratio=dto.max_consolidation_cost_ratio,
        )
        self._orchestrator.update_config(new_config)
        return self.get_config()

    def evaluate_gating(self, request: EvaluateGatingRequest) -> EvaluateGatingResponse:
        """Inspect session admission gates without state side-effects."""
        report = self._orchestrator.evaluate_session_gating(
            session_id=request.session_id,
            messages=request.messages,
            remaining_tokens=request.remaining_tokens,
            last_active_timestamp=request.last_active_timestamp,
            current_timestamp=request.current_timestamp,
            require_idle=request.require_idle,
        )
        return EvaluateGatingResponse(report=self._to_report_dto(report))

    def consolidate(self, request: ConsolidateSessionRequest) -> ConsolidateSessionResponse:
        """Execute gated auto-consolidation and return report and artifact."""
        report, artifact = self._orchestrator.consolidate_session(
            session_id=request.session_id,
            messages=request.messages,
            remaining_tokens=request.remaining_tokens,
            working_directory=request.working_directory,
            tool_call_records=request.tool_call_records,
            last_active_timestamp=request.last_active_timestamp,
            current_timestamp=request.current_timestamp,
            force_bypass_gating=request.force_bypass_gating,
            require_idle=request.require_idle,
        )

        artifact_dto: SixDimensionalMemoryArtifactDTO | None = None
        if artifact is not None:
            artifact_dto = self._to_artifact_dto(artifact)

        return ConsolidateSessionResponse(
            report=self._to_report_dto(report),
            artifact=artifact_dto,
            persisted=bool(artifact is not None),
        )

    def _to_report_dto(self, report: OverallGatingReport) -> OverallGatingReportDTO:
        return OverallGatingReportDTO(
            session_id=report.session_id,
            should_consolidate=report.should_consolidate,
            turn_decision=TurnGatingDecisionDTO(
                passed=report.turn_decision.passed,
                turn_count=report.turn_decision.turn_count,
                info_density=report.turn_decision.info_density,
                reason=report.turn_decision.reason,
            ),
            budget_decision=BudgetGatingDecisionDTO(
                passed=report.budget_decision.passed,
                remaining_tokens=report.budget_decision.remaining_tokens,
                estimated_cost_tokens=report.budget_decision.estimated_cost_tokens,
                cost_ratio=report.budget_decision.cost_ratio,
                reason=report.budget_decision.reason,
            ),
            idle_state=IdleDetectionStateDTO(
                session_id=report.idle_state.session_id,
                idle_seconds=report.idle_state.idle_seconds,
                idle_threshold_seconds=report.idle_state.idle_threshold_seconds,
                is_idle_triggered=report.idle_state.is_idle_triggered,
                reason=report.idle_state.reason,
            ),
            final_rationale=report.final_rationale,
        )

    def _to_artifact_dto(
        self,
        artifact: SixDimensionalMemoryArtifact,
    ) -> SixDimensionalMemoryArtifactDTO:
        return SixDimensionalMemoryArtifactDTO(
            artifact_id=artifact.artifact_id,
            session_id=artifact.session_id,
            created_at_iso=artifact.created_at_iso,
            working_directory=artifact.working_directory,
            key_topics=list(artifact.key_topics),
            user_preferences=list(artifact.user_preferences),
            reusable_domain_knowledge=list(artifact.reusable_domain_knowledge),
            failure_lessons=list(artifact.failure_lessons),
            tool_calling_patterns=list(artifact.tool_calling_patterns),
            token_cost=artifact.token_cost,
            summary_digest=artifact.summary_digest,
        )


_service_instance: AutoMemoryConsolidationService | None = None


def get_auto_memory_consolidation_service() -> AutoMemoryConsolidationService:
    """FastAPI dependency provider returning singleton service instance."""
    global _service_instance
    if _service_instance is None:
        _service_instance = AutoMemoryConsolidationService()
    return _service_instance
