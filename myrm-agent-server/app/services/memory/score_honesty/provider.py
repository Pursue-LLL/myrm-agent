"""Score honesty service provider for server business logic.

[POS]
Business service provider wrapping harness RetrievalScoreHonestySuite,
handling DTO transformation, dual-threshold evaluation, and singleton state.

[INPUT]
- myrm_agent_harness.toolkits.memory.score_honesty
- app.schemas.score_honesty

[OUTPUT]
- ScoreHonestyProvider
- get_score_honesty_provider
"""

from __future__ import annotations

from myrm_agent_harness.toolkits.memory.score_honesty import (
    DualThresholdConfig,
    HonestScoredCandidate,
    RetrievalScoreHonestySuite,
)

from app.schemas.score_honesty import (
    CandidateEvaluationItem,
    DualThresholdConfigDTO,
    HonestCandidateResponseDTO,
    ScoreBreakdownDTO,
    ScoreHonestyStatsDTO,
    ThresholdEvaluationVerdictDTO,
)


class ScoreHonestyProvider:
    """Server-side provider managing score honesty evaluation and diagnostics."""

    def __init__(self) -> None:
        self._suite = RetrievalScoreHonestySuite()
        self._last_stats = ScoreHonestyStatsDTO(
            total_candidates=0,
            admitted_count=0,
            rejected_count=0,
            raw_admitted_count=0,
            ranking_admitted_count=0,
            both_passed_count=0,
            divergence_count=0,
            divergence_rate=0.0,
            mean_raw_similarity=0.0,
            mean_ranking_score=0.0,
        )

    def evaluate(
        self,
        items: list[CandidateEvaluationItem],
        config_dto: DualThresholdConfigDTO | None = None,
    ) -> tuple[list[HonestCandidateResponseDTO], ScoreHonestyStatsDTO]:
        """Evaluate a list of candidate items against configured dual thresholds."""
        config = (
            DualThresholdConfig(
                raw_similarity_threshold=config_dto.raw_similarity_threshold,
                ranking_score_threshold=config_dto.ranking_score_threshold,
                strict_mode=config_dto.strict_mode,
            )
            if config_dto
            else DualThresholdConfig()
        )

        candidates: list[HonestScoredCandidate] = [
            self._suite.create_candidate(
                candidate_id=item.id,
                content=item.content,
                raw_similarity=item.raw_similarity,
                recency_factor=item.recency_factor,
                importance_boost=item.importance_boost,
                mmr_penalty=item.mmr_penalty,
                rrf_score=item.rrf_score,
                metadata=item.metadata,
            )
            for item in items
        ]

        evaluated, stats = self._suite.evaluate(candidates, config=config)

        stats_dto = ScoreHonestyStatsDTO(
            total_candidates=stats.total_candidates,
            admitted_count=stats.admitted_count,
            rejected_count=stats.rejected_count,
            raw_admitted_count=stats.raw_admitted_count,
            ranking_admitted_count=stats.ranking_admitted_count,
            both_passed_count=stats.both_passed_count,
            divergence_count=stats.divergence_count,
            divergence_rate=stats.divergence_rate,
            mean_raw_similarity=stats.mean_raw_similarity,
            mean_ranking_score=stats.mean_ranking_score,
        )
        self._last_stats = stats_dto

        response_candidates = [
            HonestCandidateResponseDTO(
                id=c.id,
                content=c.content,
                raw_similarity=c.raw_similarity,
                ranking_score=c.ranking_score,
                breakdown=ScoreBreakdownDTO(
                    raw_similarity=c.breakdown.raw_similarity,
                    recency_factor=c.breakdown.recency_factor,
                    importance_boost=c.breakdown.importance_boost,
                    mmr_penalty=c.breakdown.mmr_penalty,
                    rrf_score=c.breakdown.rrf_score,
                    final_ranking_score=c.breakdown.final_ranking_score,
                    explanation=c.breakdown.explanation,
                ),
                metadata=c.metadata,
                verdict=(
                    ThresholdEvaluationVerdictDTO(
                        passed_raw=c.verdict.passed_raw,
                        passed_ranking=c.verdict.passed_ranking,
                        admitted=c.verdict.admitted,
                        rejection_stage=c.verdict.rejection_stage.value,
                        rejection_reason=c.verdict.rejection_reason,
                    )
                    if c.verdict
                    else None
                ),
            )
            for c in evaluated
        ]

        return response_candidates, stats_dto

    def filter_admitted(
        self,
        items: list[CandidateEvaluationItem],
        config_dto: DualThresholdConfigDTO | None = None,
    ) -> list[HonestCandidateResponseDTO]:
        """Filter and return only admitted candidates."""
        evaluated, _ = self.evaluate(items, config_dto)
        return [c for c in evaluated if c.verdict and c.verdict.admitted]

    def get_stats(self) -> ScoreHonestyStatsDTO:
        """Return the latest aggregate stats."""
        return self._last_stats


_provider_instance: ScoreHonestyProvider | None = None


def get_score_honesty_provider() -> ScoreHonestyProvider:
    """Retrieve singleton provider instance."""
    global _provider_instance
    if _provider_instance is None:
        _provider_instance = ScoreHonestyProvider()
    return _provider_instance
