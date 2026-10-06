"""Service orchestrating Ebbinghaus memory decay and tiered storage lifecycle.

[INPUT]
- Candidate memory items, decay registrations, and revival requests.

[OUTPUT]
- DecayLifecycleService providing batch evaluation, reranking, and cold archival.

[POS]
- app.services.memory.decay_lifecycle_service
"""

import logging

from myrm_agent_harness.toolkits.memory.decay import (
    DecayAwareReranker,
    EbbinghausDecayScorer,
    TieredStorageLifecycleManager,
)

from app.schemas.decay_lifecycle import (
    ColdArchiveItemSchema,
    EvaluateLifecycleResponse,
    ExportColdArchiveResponse,
    RegisterMemoryDecayRequest,
    RegisterMemoryDecayResponse,
    RerankCandidatesRequest,
    RerankCandidatesResponse,
    ReviveMemoryRequest,
    ReviveMemoryResponse,
    ScoredRerankItemSchema,
)

logger = logging.getLogger(__name__)


class DecayLifecycleService:
    """Service orchestrating periodic decay evaluations, reranking, and tier archiving."""

    def __init__(self) -> None:
        self.scorer = EbbinghausDecayScorer()
        self.lifecycle_manager = TieredStorageLifecycleManager(scorer=self.scorer)
        self.reranker = DecayAwareReranker(lifecycle_manager=self.lifecycle_manager)

    def register_memory(
        self, request: RegisterMemoryDecayRequest
    ) -> RegisterMemoryDecayResponse:
        """Register a new memory item into the dynamic decay tracking manager."""
        profile = self.lifecycle_manager.register_memory(
            memory_id=request.memory_id,
            content=request.content,
            importance=request.importance,
            created_at=request.created_at,
            pinned=request.pinned,
        )

        return RegisterMemoryDecayResponse(
            memory_id=profile.memory_id,
            initial_score=profile.current_score,
            initial_tier=profile.current_tier.value,
            pinned=profile.pinned,
        )

    def evaluate_and_migrate(
        self, current_time: float | None = None
    ) -> EvaluateLifecycleResponse:
        """Trigger periodic re-evaluation and tier transitions across all tracked memories."""
        report = self.lifecycle_manager.evaluate_and_migrate(current_time=current_time)
        logger.info(
            "Decay evaluation complete: %d evaluated, %d hot, %d warm, %d cold (%d migrated)",
            report.total_evaluated,
            report.hot_count,
            report.warm_count,
            report.cold_count,
            report.migrated_count,
        )

        return EvaluateLifecycleResponse(
            total_evaluated=report.total_evaluated,
            hot_count=report.hot_count,
            warm_count=report.warm_count,
            cold_count=report.cold_count,
            migrated_count=report.migrated_count,
            migrated_memory_ids=report.migrated_memory_ids,
        )

    def rerank(
        self, request: RerankCandidatesRequest
    ) -> RerankCandidatesResponse:
        """Rerank search candidates by blending semantic similarity with Ebbinghaus decay score."""
        candidates = [
            (c.memory_id, c.content, c.base_similarity) for c in request.candidates
        ]

        reranker = DecayAwareReranker(
            lifecycle_manager=self.lifecycle_manager,
            decay_weight=request.decay_weight,
        )

        scored = reranker.rerank(
            candidates=candidates,
            exclude_cold=request.exclude_cold,
            current_time=request.current_time,
        )

        items = [
            ScoredRerankItemSchema(
                memory_id=item.memory_id,
                content=item.content,
                base_similarity=item.base_similarity,
                decay_score=item.decay_score,
                final_score=item.final_score,
                tier=item.tier.value,
            )
            for item in scored
        ]

        return RerankCandidatesResponse(total_returned=len(items), items=items)

    def revive_memory(
        self, request: ReviveMemoryRequest
    ) -> ReviveMemoryResponse | None:
        """Reactivate an archived memory item, promoting it back to the HOT tier."""
        profile = self.lifecycle_manager.revive_memory(
            memory_id=request.memory_id,
            boost_importance=request.boost_importance,
        )
        if not profile:
            return None

        return ReviveMemoryResponse(
            memory_id=profile.memory_id,
            new_score=profile.current_score,
            new_tier=profile.current_tier.value,
            access_count=profile.access_count,
        )

    def export_cold_archive(self) -> ExportColdArchiveResponse:
        """Export serialized records of all cold archived memories."""
        raw_records = self.lifecycle_manager.export_cold_archive()
        records = [
            ColdArchiveItemSchema(
                memory_id=str(r["memory_id"]),
                content=str(r["content"]),
                importance=float(r["importance"]),
                created_at=float(r["created_at"]),
                last_accessed_at=float(r["last_accessed_at"]),
                access_count=int(r["access_count"]),
                pinned=bool(r["pinned"]),
                score=float(r["score"]),
                tier=str(r["tier"]),
            )
            for r in raw_records
        ]
        return ExportColdArchiveResponse(total_archived=len(records), records=records)


# Global singleton instance
decay_lifecycle_service = DecayLifecycleService()
