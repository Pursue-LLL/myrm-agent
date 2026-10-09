"""Business service implementing Two-Layer Context Injection & Multi-Pass Dialectic Reconciliation (Item 112).

[POS]
app/services/memory/two_layer_dialectic_service.py

[INPUT]
- app.schemas.two_layer_dialectic, myrm_agent_harness.toolkits.memory

[OUTPUT]
- TwoLayerDialecticService, get_two_layer_dialectic_service
"""


from __future__ import annotations

import logging
from functools import lru_cache

from myrm_agent_harness.toolkits.memory import (
    BaseContextPayload,
    DialecticConflictCandidate,
    DialecticReconciliationConfig,
    DialecticReconciliationResult,
    MultiPassDialecticReconciler,
    TwoLayerContextInjectionResult,
    TwoLayerContextInjector,
)

from app.schemas.two_layer_dialectic import (
    AssembleInjectionRequest,
    BaseContextPayloadDTO,
    DialecticConflictCandidateDTO,
    DialecticReconciliationResultDTO,
    TwoLayerContextInjectionResultDTO,
)

logger = logging.getLogger(__name__)


def _candidate_to_dto(c: DialecticConflictCandidate) -> DialecticConflictCandidateDTO:
    """Map harness conflict candidate to API DTO."""
    return DialecticConflictCandidateDTO(
        statement_a=c.statement_a,
        statement_b=c.statement_b,
        subject_domain=c.subject_domain,
        conflict_score=c.conflict_score,
    )


def _result_to_dto(r: DialecticReconciliationResult) -> DialecticReconciliationResultDTO:
    """Map harness reconciliation result to API DTO."""
    return DialecticReconciliationResultDTO(
        passes_executed=[p.value if hasattr(p, "value") else str(p) for p in r.passes_executed],
        resolved_statement=r.resolved_statement,
        superseded_statements=r.superseded_statements,
        confidence=r.confidence,
        rationale=r.rationale,
    )


def _base_payload_to_dto(p: BaseContextPayload) -> BaseContextPayloadDTO:
    """Map harness base context payload to API DTO."""
    return BaseContextPayloadDTO(
        session_summary=p.session_summary,
        standing_peer_cards=p.standing_peer_cards,
        cache_control_hash=p.cache_control_hash,
        refreshed_at_turn=p.refreshed_at_turn,
        created_at=p.created_at,
    )


def _injection_result_to_dto(res: TwoLayerContextInjectionResult) -> TwoLayerContextInjectionResultDTO:
    """Map harness injection result to API DTO."""
    return TwoLayerContextInjectionResultDTO(
        layer1_base_context=res.layer1_base_context,
        layer2_dialectic_block=res.layer2_dialectic_block,
        injected_position=res.injected_position,
        is_cache_safe=res.is_cache_safe,
        token_overhead=res.token_overhead,
    )


class TwoLayerDialecticService:
    """Domain service managing Prompt Cache preservation and dialectic contradiction resolution."""

    def __init__(self, injector: TwoLayerContextInjector | None = None) -> None:
        self._injector = injector or TwoLayerContextInjector()

    @property
    def injector(self) -> TwoLayerContextInjector:
        return self._injector

    def inspect_conflicts(
        self, statements: list[str], cutoff: float = 0.65
    ) -> list[DialecticConflictCandidateDTO]:
        """Scan candidate statements for mutual exclusivity."""
        cfg = DialecticReconciliationConfig(conflict_similarity_cutoff=cutoff)
        reconciler = MultiPassDialecticReconciler(cfg)
        conflicts = reconciler.inspect_conflicts(statements)
        return [_candidate_to_dto(c) for c in conflicts]

    def reconcile_conflicts(
        self, statements: list[str], depth: int = 3
    ) -> list[DialecticReconciliationResultDTO]:
        """Execute multi-pass dialectic resolution over statements."""
        cfg = DialecticReconciliationConfig(dialectic_depth=depth)
        reconciler = MultiPassDialecticReconciler(cfg)
        results = reconciler.reconcile_all(statements, depth=depth)
        return [_result_to_dto(r) for r in results]

    def assemble_injection(
        self, request: AssembleInjectionRequest
    ) -> TwoLayerContextInjectionResultDTO:
        """Compose dual-layer context blocks under cadence controls."""
        if (
            self._injector.config.context_cadence != request.context_cadence
            or self._injector.config.dialectic_cadence != request.dialectic_cadence
        ):
            custom_config = DialecticReconciliationConfig(
                context_cadence=request.context_cadence,
                dialectic_cadence=request.dialectic_cadence,
            )
            injector = TwoLayerContextInjector(custom_config)
        else:
            injector = self._injector

        res = injector.assemble_injection(
            session_id=request.session_id,
            turn=request.turn,
            session_summary=request.session_summary,
            peer_cards=request.peer_cards,
            candidate_memories=request.candidate_memories,
            force_refresh_base=request.force_refresh_base,
            force_dialectic=request.force_dialectic,
        )
        return _injection_result_to_dto(res)

    def get_base_context_cache(self, session_id: str) -> BaseContextPayloadDTO | None:
        """Retrieve cached Layer 1 base context payload if present."""
        cached = self._injector.get_cached_base_context(session_id)
        if cached is None:
            return None
        return _base_payload_to_dto(cached)

    def reset_session_cadence(self, session_id: str) -> bool:
        """Evict cadence cache for session."""
        self._injector.reset_session(session_id)
        return True


@lru_cache(maxsize=1)
def get_two_layer_dialectic_service() -> TwoLayerDialecticService:
    """Provide singleton TwoLayerDialecticService instance."""
    return TwoLayerDialecticService()
