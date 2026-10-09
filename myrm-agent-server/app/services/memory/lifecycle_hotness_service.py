"""[POS]: app/services/memory/lifecycle_hotness_service.py
[INPUT]: API request payloads for single entity hotness calculation and batch blended reranking.
[OUTPUT]: LifecycleHotnessService business facade coordinating harness memory hotness scorer.
"""

from myrm_agent_harness.toolkits.memory import (
    BatchLifecycleClassificationResult,
    HotnessLifecycleStage,
    HotnessScoringConfig,
    MemoryHotnessScorer,
    MemoryLifecycleItem,
    compute_hotness_score,
)

from app.schemas.lifecycle_hotness import (
    BlendRerankRequest,
    BlendRerankResponse,
    HotnessLifecycleStageAPI,
    MemoryLifecycleItemPayload,
    SingleScoreRequest,
    SingleScoreResponse,
)


class LifecycleHotnessService:
    """Service facade managing memory hotness scoring, exponential time decay, and blended reranking."""

    def score_single(self, request: SingleScoreRequest) -> SingleScoreResponse:
        """Compute deterministic hotness score and classify lifecycle stage for a single memory entity."""
        score = compute_hotness_score(
            active_count=request.active_count,
            updated_at=request.updated_at,
            now=request.now,
            half_life_days=request.half_life_days,
        )

        config = HotnessScoringConfig(default_half_life_days=request.half_life_days)
        scorer = MemoryHotnessScorer(config=config)
        stage: HotnessLifecycleStage = scorer.classify(score)

        return SingleScoreResponse(
            active_count=request.active_count,
            updated_at=request.updated_at,
            hotness_score=score,
            lifecycle_stage=HotnessLifecycleStageAPI(stage.value),
        )

    def blend_rerank(self, request: BlendRerankRequest) -> BlendRerankResponse:
        """Execute blended reranking across candidate memory items, updating their lifecycle stages."""
        config = HotnessScoringConfig(
            default_half_life_days=request.half_life_days,
            blend_alpha=request.blend_alpha,
        )
        scorer = MemoryHotnessScorer(config=config)

        harness_items = [
            MemoryLifecycleItem(
                id=item.id,
                active_count=item.active_count,
                updated_at=item.updated_at,
                semantic_score=item.semantic_score,
                metadata=item.metadata,
            )
            for item in request.items
        ]

        result: BatchLifecycleClassificationResult = scorer.rerank_and_classify_batch(
            harness_items,
            now=request.now,
        )

        payload_items = [
            MemoryLifecycleItemPayload(
                id=it.id,
                active_count=it.active_count,
                updated_at=it.updated_at,
                semantic_score=it.semantic_score,
                hotness_score=it.hotness_score,
                blended_score=it.blended_score,
                lifecycle_stage=HotnessLifecycleStageAPI(it.lifecycle_stage.value),
                metadata=it.metadata,
            )
            for it in result.items
        ]

        return BlendRerankResponse(
            items=payload_items,
            cold_count=result.cold_count,
            warm_count=result.warm_count,
            hot_count=result.hot_count,
            avg_hotness=result.avg_hotness,
        )


_instance: LifecycleHotnessService | None = None


def get_lifecycle_hotness_service() -> LifecycleHotnessService:
    """Singleton provider for LifecycleHotnessService."""
    global _instance
    if _instance is None:
        _instance = LifecycleHotnessService()
    return _instance
