"""
[POS] app/services/memory/auto_recall_service.py
[INPUT] app/schemas/auto_recall.py, myrm_agent_harness.toolkits.memory.auto_recall
[OUTPUT] AutoRecallService, get_auto_recall_service
"""

from __future__ import annotations

from myrm_agent_harness.toolkits.memory.auto_recall import (
    AutoRecallDecision,
    ExperienceRecallGate,
    RecallCandidate,
    RecallGateConfig,
)

from app.schemas.auto_recall import (
    AutoRecallDecisionResponse,
    AutoRecallEvaluateRequest,
    RecallCandidateDTO,
    SessionClearResponse,
    SlidingWindowStatsResponse,
)


class AutoRecallService:
    """Service mediating targeted experience auto-recall gate orchestration."""

    def __init__(self, gate: ExperienceRecallGate | None = None) -> None:
        self._gate = gate or ExperienceRecallGate(
            config=RecallGateConfig(dedup_turns=5, reranker_timeout_ms=800.0)
        )

    def evaluate_and_recall(
        self, req: AutoRecallEvaluateRequest
    ) -> AutoRecallDecisionResponse:
        """Evaluate incoming turn signals, dedup across turns, and rerank candidates."""
        domain_candidates = [
            RecallCandidate(
                memory_id=c.memory_id,
                content=c.content,
                initial_score=c.initial_score,
                metadata=c.metadata,
            )
            for c in req.raw_candidates
        ]

        decision: AutoRecallDecision = self._gate.evaluate_and_recall(
            session_id=req.session_id,
            current_turn=req.current_turn,
            raw_candidates=domain_candidates,
            event_name=req.event_name,
            tool_name=req.tool_name,
            query_text=req.query_text,
            force_recall=req.force_recall,
        )

        serialized_injected = [
            RecallCandidateDTO(
                memory_id=c.memory_id,
                content=c.content,
                initial_score=c.initial_score,
                metadata=c.metadata,
            )
            for c in decision.injected_candidates
        ]

        return AutoRecallDecisionResponse(
            triggered=decision.triggered,
            trigger_type=str(decision.trigger_type),
            candidates_pre_dedup=decision.candidates_pre_dedup,
            candidates_post_dedup=decision.candidates_post_dedup,
            injected_candidates=serialized_injected,
            reranker_status=str(decision.reranker_status),
            audit_reason=decision.audit_reason,
        )

    def get_sliding_window_stats(self, session_id: str) -> SlidingWindowStatsResponse:
        """Query active sliding window suppression statistics for a session."""
        stats = self._gate.get_dedup_gate().get_session_stats(session_id)
        return SlidingWindowStatsResponse(
            session_id=session_id,
            active_window_turns=stats.get("active_window_turns", 0),
            total_suppressed_id_count=stats.get("total_suppressed_id_count", 0),
        )

    def clear_session(self, session_id: str) -> SessionClearResponse:
        """Purge sliding window state for a finished or reset session."""
        self._gate.get_dedup_gate().clear_session(session_id)
        return SessionClearResponse(session_id=session_id, cleared=True)


_SERVICE_INSTANCE: AutoRecallService | None = None


def get_auto_recall_service() -> AutoRecallService:
    """Return singleton instance of AutoRecallService."""
    global _SERVICE_INSTANCE
    if _SERVICE_INSTANCE is None:
        _SERVICE_INSTANCE = AutoRecallService()
    return _SERVICE_INSTANCE
