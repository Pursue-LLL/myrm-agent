"""Service orchestrating Ebbinghaus memory decay and tiered storage lifecycle.

[INPUT]
- Lifecycle evaluation and revival requests.

[OUTPUT]
- DecayLifecycleService providing batch evaluation, revival, and cold archival.

[POS]
- app.services.memory.decay_lifecycle_service
"""

import logging

from myrm_agent_harness.toolkits.memory.decay import (
    EbbinghausDecayScorer,
    TieredStorageLifecycleManager,
)

from app.schemas.decay_lifecycle import (
    ColdArchiveItemSchema,
    EvaluateLifecycleResponse,
    ExportColdArchiveResponse,
    ReviveMemoryRequest,
    ReviveMemoryResponse,
)

logger = logging.getLogger(__name__)


class DecayLifecycleService:
    """Service orchestrating periodic decay evaluations, tier migrations, revival, and cold archiving."""

    def __init__(self) -> None:
        self.scorer = EbbinghausDecayScorer()
        self.lifecycle_manager = TieredStorageLifecycleManager(scorer=self.scorer)

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
